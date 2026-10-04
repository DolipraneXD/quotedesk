import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import { upload } from './quotes'

export interface Backup {
  name: string
  kind: 'database' | 'full'
  size: number
  created_at: string
}

const backupsKey = ['backups'] as const

export const backupDownloadUrl = (name: string) =>
  `/api/v1/backups/${encodeURIComponent(name)}/download`

export function useBackups() {
  return useQuery({ queryKey: backupsKey, queryFn: () => api<Backup[]>('GET', '/backups') })
}

export function useBackupActions() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: backupsKey })
  return {
    create: useMutation({
      mutationFn: (full: boolean) => api<Backup>('POST', '/backups', { body: { full } }),
      onSuccess: refresh,
    }),
    upload: useMutation({
      mutationFn: (file: File) => upload<Backup>('/backups/upload', 'file', [file]),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (name: string) => api<void>('DELETE', `/backups/${encodeURIComponent(name)}`),
      onSuccess: refresh,
    }),
    /** Every screen's data changes with a restore: drop the whole cache. */
    restore: useMutation({
      mutationFn: (name: string) =>
        api<Backup | null>('POST', `/backups/${encodeURIComponent(name)}/restore`),
      onSuccess: () => qc.invalidateQueries(),
    }),
  }
}
