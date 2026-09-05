/**
 * Unsaved editor input, kept across a forced sign-out.
 *
 * When a 401 arrives while an editor is open the router navigates to /login, and
 * React unmounts the dialog — component state does not survive that. So the draft
 * is written here, outside the tree, and restored when the owner comes back.
 *
 * Module-scoped rather than in localStorage on purpose: a draft can contain the
 * owner's private plan, and it should not outlive the tab it was typed in.
 */

const drafts = new Map<string, unknown>()

export function saveDraft(key: string, value: unknown): void {
  drafts.set(key, value)
}

export function readDraft<T>(key: string): T | undefined {
  return drafts.get(key) as T | undefined
}

export function clearDraft(key: string): void {
  drafts.delete(key)
}

/** Called on sign-out: the next owner of this tab must not see the previous drafts. */
export function clearAllDrafts(): void {
  drafts.clear()
}

export function draftCount(): number {
  return drafts.size
}
