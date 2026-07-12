export type RoleKey = "leader" | "product" | "architect" | "engineer" | "data" | "reviewer" | "validator" | "user" | "renderer";

export const ROLE_META: Record<RoleKey, { label: string; short: string }> = {
  leader: { label: "Team Leader", short: "TL" },
  product: { label: "Product Manager", short: "PM" },
  architect: { label: "Architect", short: "AR" },
  engineer: { label: "Engineer", short: "EN" },
  data: { label: "Data Analyst", short: "DA" },
  reviewer: { label: "Reviewer", short: "RV" },
  validator: { label: "Validator", short: "VA" },
  user: { label: "You", short: "YOU" },
  renderer: { label: "Renderer", short: "RE" },
};

export function AtomLogo() {
  return <span className="atom-logo" aria-label="Another Atom logo">
    <i className="atom-orbit orbit-one" /><i className="atom-orbit orbit-two" />
    <i className="atom-dot dot-product" /><i className="atom-dot dot-architect" />
    <i className="atom-dot dot-engineer" /><i className="atom-dot dot-data" />
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
