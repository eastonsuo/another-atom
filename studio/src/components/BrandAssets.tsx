export type RoleKey = "product" | "designer" | "engineer" | "qa" | "user" | "renderer";

export const ROLE_META: Record<RoleKey, { label: string; short: string }> = {
  product: { label: "Product Manager", short: "PM" },
  designer: { label: "Designer", short: "DS" },
  engineer: { label: "Engineer", short: "EN" },
  qa: { label: "QA", short: "QA" },
  user: { label: "You", short: "YOU" },
  renderer: { label: "Renderer", short: "RE" },
};

export function AtomLogo() {
  return <span className="atom-logo" aria-label="Another Atom logo">
    <i className="atom-orbit orbit-one" /><i className="atom-orbit orbit-two" />
    <i className="atom-dot dot-product" /><i className="atom-dot dot-designer" />
    <i className="atom-dot dot-engineer" /><i className="atom-dot dot-qa" />
    <b>A</b>
  </span>;
}

export function RoleAvatar({ role, size = "medium" }: { role: RoleKey; size?: "small" | "medium" | "large" | "hero" }) {
  return <span className={`role-avatar role-${role} avatar-${size}`} aria-label={ROLE_META[role].label} title={ROLE_META[role].label}>
    <i className="role-ear ear-left" /><i className="role-ear ear-right" />
    <span className="role-face"><i className="role-eye eye-left" /><i className="role-eye eye-right" /><i className="role-smile" /></span>
    <b>{ROLE_META[role].short}</b>
  </span>;
}
