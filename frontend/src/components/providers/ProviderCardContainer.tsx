import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, type ProviderProfile } from '../../api/client'
import { ProviderCard } from './ProviderCard'
import { ProviderErrorPanel } from './ProviderError'

export function ProviderCardContainer({ provider, onEdit }: { provider: ProviderProfile; onEdit: () => void }) {
  const queryClient = useQueryClient()
  const [actionError, setActionError] = useState<unknown>()
  const models = useQuery({
    queryKey: ['provider-models', provider.id],
    queryFn: () => api.listModels(provider.id),
  })

  async function refresh() {
    setActionError(undefined)
    try {
      const refreshed = await api.refreshModels(provider.id, true)
      queryClient.setQueryData(['provider-models', provider.id], refreshed)
    } catch (error) {
      setActionError(error)
    }
  }

  async function mutateProvider(action: () => Promise<unknown>) {
    setActionError(undefined)
    try {
      await action()
      await queryClient.invalidateQueries({ queryKey: ['providers'] })
    } catch (error) {
      setActionError(error)
    }
  }

  async function remove() {
    if (!window.confirm(`确定删除“${provider.name}”吗？已保存的密钥和模型记录也会删除。`)) return
    setActionError(undefined)
    try {
      await api.deleteProvider(provider.id)
      queryClient.removeQueries({ queryKey: ['provider-models', provider.id] })
      await queryClient.invalidateQueries({ queryKey: ['providers'] })
    } catch (error) {
      setActionError(error)
    }
  }

  return (
    <div className="provider-card-wrap">
      <ProviderCard
        provider={provider}
        models={models.data ?? []}
        onEdit={onEdit}
        onRefresh={() => void refresh()}
        onToggle={() => void mutateProvider(() => provider.enabled ? api.disableProvider(provider.id) : api.enableProvider(provider.id))}
        onDefault={() => void mutateProvider(() => api.setDefaultProvider(provider.id))}
        onDelete={() => void remove()}
      />
      {(models.error !== null || actionError !== undefined) && <ProviderErrorPanel error={actionError ?? models.error} />}
    </div>
  )
}
