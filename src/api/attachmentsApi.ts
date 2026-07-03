import { API_BASE, authHeaders } from './client'

export interface UploadedAttachment {
  name: string
  /** 프록시(/api)를 포함한, 마크다운에 바로 넣을 수 있는 URL */
  url: string
}

const IMAGE_EXT = /\.(png|jpe?g|gif|webp|svg|bmp|avif)$/i

export function isImageFile(name: string): boolean {
  return IMAGE_EXT.test(name)
}

/** 파일을 raw body로 업로드하고 마크다운용 URL을 돌려준다. */
export async function uploadAttachment(file: File): Promise<UploadedAttachment> {
  const res = await fetch(
    `${API_BASE}/attachments?filename=${encodeURIComponent(file.name)}`,
    {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/octet-stream' }),
      body: file,
    },
  )
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`API ${res.status}: ${err}`)
  }
  const body = (await res.json()) as { name: string; url: string }
  return { name: body.name, url: `${API_BASE}${body.url}` }
}

/** 업로드 결과를 마크다운 조각으로 변환 (이미지는 ! 문법). */
export function attachmentMarkdown(a: UploadedAttachment): string {
  return isImageFile(a.name) ? `![${a.name}](${a.url})` : `[${a.name}](${a.url})`
}
