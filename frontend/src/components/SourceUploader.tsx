import { FileUp, UploadCloud } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'

const accepted = '.pdf,.doc,.docx,.ppt,.pptx,.txt,.md'

export function SourceUploader({ busy, onUpload }: { busy: boolean; onUpload: (file: File) => void }) {
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files[0]
    if (file) onUpload(file)
  }

  return (
    <section className="source-uploader" aria-labelledby="source-upload-title">
      <div className="section-heading">
        <div><p className="eyebrow">资料入库</p><h2 id="source-upload-title">把复习材料放进项目</h2></div>
        <span className="binding-status">原文件留在本机</span>
      </div>
      <div
        className={`source-drop-zone${dragging ? ' is-dragging' : ''}`}
        data-testid="source-drop-zone"
        onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
      >
        <UploadCloud aria-hidden="true" />
        <strong>{busy ? '正在解析资料…' : '拖放文件到这里，或从电脑选择'}</strong>
        <p>支持 PDF、Word、PPT、TXT 和 Markdown；旧版 DOC / PPT 会尝试通过 Office 转换。</p>
        <button className="button button--primary" type="button" disabled={busy} onClick={() => input.current?.click()}><FileUp /> 选择文件</button>
        <input ref={input} className="visually-hidden" type="file" accept={accepted} aria-label="选择资料文件" disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) onUpload(file); event.currentTarget.value = '' }} />
      </div>
      <div className="upload-rules" aria-label="上传限制">
        <span>单个文件最多 100 MB</span><span>一次选择一个文件</span><span>解析后可逐块勾选</span>
      </div>
    </section>
  )
}
