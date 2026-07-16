import { ApiError } from '../../api/client'

const actions: Record<string, string> = {
  upstream_auth_failed: '重新填写 API Key 后再试。',
  upstream_forbidden: '检查账户权限和模型授权。',
  upstream_endpoint_not_found: '核对 API 地址，或在下方手动填写模型。',
  upstream_rate_limited: '稍后重试，或检查服务额度。',
  provider_not_validated: '先完成模型能力校验。',
}

export function ProviderErrorPanel({ error }: { error: unknown }) {
  const apiError = error instanceof ApiError ? error : null
  const message = error instanceof Error ? error.message : '操作未完成。'
  return <div className="provider-error" role="alert"><strong>{message}</strong><p>{actions[apiError?.code ?? ''] ?? '检查当前填写内容后重试。'}</p>{apiError && <details><summary>技术详情</summary><code>{apiError.code ?? 'unknown'} · HTTP {apiError.status}</code></details>}</div>
}
