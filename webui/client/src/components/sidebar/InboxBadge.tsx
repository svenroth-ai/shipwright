interface InboxBadgeProps {
  count: number;
}

export function InboxBadge({ count }: InboxBadgeProps) {
  if (count === 0) return null;

  const display = count > 99 ? '99+' : String(count);

  return (
    <span className="min-w-[18px] h-[18px] rounded-full bg-red-500 text-white text-[11px] font-semibold flex items-center justify-center px-1">
      {display}
    </span>
  );
}
