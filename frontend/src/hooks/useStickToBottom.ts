import { useEffect, useRef, type RefObject } from "react"

/**
 * 让滚动容器在「用户已经在底部」时跟随新内容滚到底；用户主动上滑查看历史时不打扰。
 *
 * - 直接设置 `scrollTop`（瞬时），避免 smooth 滚动与每个流式 delta 抢拍造成的上下抖动。
 * - `signature` 应当只在「真实内容增长」时变化（见 streamSignature）；这样
 *   展开/收起思维链等纯 UI 切换不会触发滚动（修复"展开思维链就自动吸底"）。
 */
export function useStickToBottom(
  scrollRef: RefObject<HTMLElement | null>,
  signature: string | number,
  opts: { threshold?: number } = {},
) {
  const threshold = opts.threshold ?? 80
  const stick = useRef(true)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onScroll = () => {
      const dist = el.scrollHeight - el.scrollTop - el.clientHeight
      stick.current = dist <= threshold
    }
    el.addEventListener("scroll", onScroll, { passive: true })
    return () => el.removeEventListener("scroll", onScroll)
  }, [scrollRef, threshold])

  useEffect(() => {
    if (!stick.current) return
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [scrollRef, signature])
}

/**
 * 由消息线程计算"内容签名"：仅随消息数、正文/思维链长度、Agent 步数变化，
 * 不随 showThinking 等 UI 状态变化 —— 这样跟随只在真有新内容时发生。
 */
export function streamSignature(
  msgs: ReadonlyArray<{ content: string; thinking: string; agentSteps: ReadonlyArray<unknown> }>,
): string {
  let len = 0
  for (const m of msgs) len += m.content.length + m.thinking.length + m.agentSteps.length
  return `${msgs.length}:${len}`
}
