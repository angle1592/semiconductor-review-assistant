import { Ban, RefreshCw, RotateCcw } from 'lucide-react'

import type { AnalysisRun } from '../api/analysis'

const labels: Record<string, string> = { queued: '等待 worker 接手', running: '正在提取重点', partial: '部分批次未完成', succeeded: '分析完成，等待你确认', failed: '分析未完成', cancelled: '分析已取消' }
const terminal = new Set(['partial', 'succeeded', 'failed', 'cancelled'])

export function AnalysisProgress({ run, pending, onCancel, onRetry }: { run: AnalysisRun; pending: boolean; onCancel: () => void; onRetry: () => void }) {
  const progress = run.total_batches ? Math.round((run.completed_batches / run.total_batches) * 100) : 0
  return (
    <section className="analysis-progress" aria-live="polite">
      <div className="section-heading"><div><p className="eyebrow">后台任务 #{run.id}</p><h2>{labels[run.status] ?? run.status}</h2></div><strong>{progress}%</strong></div>
      <div className="progress-track" role="progressbar" aria-label="分析进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><span style={{ width: `${progress}%` }} /></div>
      <p>已完成 {run.completed_batches} / {run.total_batches} 批{run.failed_batches ? `，失败 ${run.failed_batches} 批` : ''}。关闭页面不会停止任务。</p>
      <div className="batch-strip" aria-label="批次状态">
        {run.batches.map((batch) => <span key={batch.id} className={`batch-tick is-${batch.status}`} title={`第 ${batch.ordinal + 1} 批：${batch.status}`}>{batch.ordinal + 1}</span>)}
      </div>
      {(run.error_detail || run.public_error_code) && <div className="source-warning"><Ban /><div><strong>{run.public_error_code ?? '分析出错'}</strong><p>{run.error_detail ?? '可重试失败批次，已成功的结果不会丢失。'}</p></div></div>}
      <div className="candidate-toolbar">
        {!terminal.has(run.status) && <button className="button button--danger" type="button" disabled={pending || run.cancellation_requested} onClick={onCancel}><Ban /> 取消分析</button>}
        {(run.status === 'partial' || run.status === 'failed') && <button className="button button--secondary" type="button" disabled={pending} onClick={onRetry}><RotateCcw /> 重试失败批次</button>}
        {run.status === 'running' && <span className="binding-status"><RefreshCw className="spin" /> 自动刷新中</span>}
      </div>
    </section>
  )
}
