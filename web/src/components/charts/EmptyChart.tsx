export default function EmptyChart({ label }: { label: string }) {
  return (
    <div className="flex h-32 items-center justify-center text-center text-xs text-slate-600">
      {label}
    </div>
  );
}
