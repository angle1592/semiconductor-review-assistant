import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, BookOpenText, FileText, Plus, Upload } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { api, previewUrl, type CourseDocument } from '../api/client'
import { ErrorState, LoadingState, PageHeading } from '../components/Ui'

export function CourseDetailPage() {
  const { id = '' } = useParams()
  const queryClient = useQueryClient()
  const [uploadedDocument, setUploadedDocument] = useState<CourseDocument | null>(null)
  const [notebookOpen, setNotebookOpen] = useState(false)
  const [notebookTitle, setNotebookTitle] = useState('NotebookLM 学习指南')
  const [notebookText, setNotebookText] = useState('')
  const [sourceFilename, setSourceFilename] = useState<string | undefined>()
  const [notice, setNotice] = useState('')
  const [importedNotebookId, setImportedNotebookId] = useState('')
  const course = useQuery({ queryKey: ['course', id], queryFn: () => api.getCourse(id), enabled: Boolean(id) })
  const documents = useQuery({
    queryKey: ['documents', id],
    queryFn: () => api.listDocuments(id),
    enabled: Boolean(id),
    retry: false,
  })
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadDocument(id, file),
    onSuccess: (document) => {
      setUploadedDocument(document)
      setNotice(`已导入 ${document.original_filename}，共 ${document.page_count} 页。`)
      void queryClient.invalidateQueries({ queryKey: ['documents', id] })
    },
  })
  const notebook = useMutation({
    mutationFn: () =>
      api.importNotebook(id, {
        title: notebookTitle.trim(),
        raw_text: notebookText,
        source_filename: sourceFilename,
      }),
    onSuccess: (created) => {
      setNotice('NotebookLM 原文已完整保存在本机。')
      setImportedNotebookId(created.id)
      setNotebookText('')
      setSourceFilename(undefined)
      setNotebookOpen(false)
    },
  })

  const visibleDocuments = documents.data ?? (uploadedDocument ? [uploadedDocument] : [])

  async function readNotebookFile(file?: File) {
    if (!file) return
    setNotebookText(await file.text())
    setSourceFilename(file.name)
    setNotebookTitle(file.name.replace(/\.(md|txt)$/i, '') || 'NotebookLM 导入')
  }

  if (course.isPending) return <LoadingState label="正在打开课程档案" />
  if (course.isError || !course.data) {
    return <ErrorState title="课程档案不存在" description="返回课程列表，确认课程是否仍保存在本机。" />
  }

  return (
    <div>
      <Link className="back-link" to="/courses"><ArrowLeft aria-hidden="true" /> 返回课程</Link>
      <PageHeading
        eyebrow="课程档案"
        title={course.data.title}
        description={course.data.description || '在这里汇总课件页面与课堂来源。'}
        actions={<Link className="button button--primary" to={`/lessons/new?course=${id}`}><Plus /> 记录新课</Link>}
      />

      {notice && <div className="notice notice--success" role="status">{notice}</div>}
      {importedNotebookId && (
        <div className="form-actions">
          <Link className="button button--secondary" to={`/lessons/new?course=${id}&notebook=${importedNotebookId}`}>
            用这份指南生成复习
          </Link>
        </div>
      )}

      <section className="ingest-grid">
        <label className={`drop-panel${upload.isPending ? ' is-busy' : ''}`}>
          <Upload aria-hidden="true" />
          <strong>{upload.isPending ? '正在逐页处理…' : '导入 PDF / PowerPoint'}</strong>
          <span>PDF 直接处理；PPT/PPTX 使用本机 PowerPoint 转换。</span>
          <input
            type="file"
            accept=".pdf,.ppt,.pptx,application/pdf,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation"
            disabled={upload.isPending}
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) upload.mutate(file)
              event.target.value = ''
            }}
          />
        </label>
        <button className="drop-panel drop-panel--button" type="button" onClick={() => setNotebookOpen((open) => !open)}>
          <BookOpenText aria-hidden="true" />
          <strong>导入 NotebookLM 原文</strong>
          <span>粘贴或读取 Markdown / TXT，原文和来源不会被改写。</span>
        </button>
      </section>

      {upload.isError && (
        <div className="notice notice--error" role="alert">
          课件未导入。若是 PowerPoint，请确认本机已安装 PowerPoint，或先另存为 PDF。
        </div>
      )}

      {notebookOpen && (
        <section className="inline-form-panel">
          <div className="section-heading">
            <div><p className="eyebrow">外部学习材料</p><h2>保留 NotebookLM 原文</h2></div>
            <label className="button button--secondary file-button">
              读取文件
              <input type="file" accept=".md,.txt,text/markdown,text/plain" onChange={(event) => void readNotebookFile(event.target.files?.[0])} />
            </label>
          </div>
          <div className="form-grid">
            <label>标题<input value={notebookTitle} onChange={(event) => setNotebookTitle(event.target.value)} /></label>
            <label className="form-span">原文<textarea rows={10} value={notebookText} onChange={(event) => setNotebookText(event.target.value)} /></label>
            {sourceFilename && <p className="file-source">来源文件：{sourceFilename}</p>}
            {notebook.isError && <p className="form-error">内容未保存，请确认本地服务已启动。</p>}
            <div className="form-actions form-span">
              <button className="button button--primary" type="button" disabled={!notebookTitle.trim() || !notebookText || notebook.isPending} onClick={() => notebook.mutate()}>
                {notebook.isPending ? '正在保存…' : '保存原文'}
              </button>
              <button className="button button--ghost" type="button" onClick={() => setNotebookOpen(false)}>取消</button>
            </div>
          </div>
        </section>
      )}

      <section className="document-section">
        <div className="section-heading">
          <div><p className="eyebrow">页面来源</p><h2>已导入课件</h2></div>
          <span className="quiet-count">{visibleDocuments.length} 份</span>
        </div>
        {documents.isPending && <LoadingState label="正在读取课件索引" />}
        {documents.isError && !uploadedDocument && (
          <div className="notice">课件索引接口尚未就绪；新上传的课件仍会立即显示在这里。</div>
        )}
        {!documents.isPending && visibleDocuments.length === 0 && (
          <div className="document-empty"><FileText aria-hidden="true" /><p>导入第一份课件后，可逐页预览并记录当天范围。</p></div>
        )}
        {visibleDocuments.map((document) => (
          <article className="document-card" key={document.id}>
            <div className="document-meta">
              <div>
                <span className="file-type">{document.file_type.toUpperCase()}</span>
                <h3>{document.original_filename}</h3>
                <p>{document.page_count} 页 · 已保留页面来源</p>
              </div>
              <Link className="button button--secondary" to={`/lessons/new?course=${id}&document=${document.id}`}>选择当天页面</Link>
            </div>
            {document.pages.length > 0 && (
              <div className="page-strip">
                {document.pages.slice(0, 8).map((page) => (
                  <figure key={page.id}>
                    <img src={previewUrl(page.preview_url)} alt={`${document.original_filename} 第 ${page.page_number} 页`} loading="lazy" />
                    <figcaption>P.{page.page_number}</figcaption>
                  </figure>
                ))}
                {document.pages.length > 8 && <div className="more-pages">+{document.pages.length - 8}<span>页</span></div>}
              </div>
            )}
          </article>
        ))}
      </section>
    </div>
  )
}
