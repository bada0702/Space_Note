import { Marked } from 'marked'

const ESCAPES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
const escapeHtml = (s: string) => s.replace(/[&<>"']/g, c => ESCAPES[c])
const SAFE_URL = /^(https?:|mailto:|#|\/)/i

// AI 답변용 — 모델이 노트·외부 대화를 그대로 옮겨 적을 수 있으므로 원시 HTML은 글자로 보여 주고,
// javascript: 같은 위험한 주소의 링크·이미지는 텍스트로만 남긴다
const chatMarked = new Marked({
  gfm: true,
  breaks: true,
  renderer: {
    html(html: string) {
      return escapeHtml(html)
    },
    link(href: string, title: string | null | undefined, text: string) {
      if (!SAFE_URL.test(href)) return text
      const t = title ? ` title="${escapeHtml(title)}"` : ''
      return `<a href="${escapeHtml(href)}"${t} target="_blank" rel="noopener noreferrer">${text}</a>`
    },
    image(href: string, _title: string | null, text: string) {
      return SAFE_URL.test(href) ? false : escapeHtml(text)
    },
  },
})

export function renderChatMarkdown(src: string): string {
  return chatMarked.parse(src) as string
}
