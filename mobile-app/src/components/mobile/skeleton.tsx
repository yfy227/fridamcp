/**
 * 骨架屏组件
 * 用于列表加载、卡片加载等场景
 */

export function AppListSkeleton() {
  return (
    <div className="space-y-2.5">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 p-3 rounded-2xl bg-card border border-border">
          <div className="w-11 h-11 rounded-2xl bg-muted/50 animate-pulse shrink-0" />
          <div className="flex-1 space-y-2">
            <div className="h-3.5 w-24 bg-muted/50 rounded animate-pulse" />
            <div className="h-2.5 w-40 bg-muted/40 rounded animate-pulse" />
          </div>
          <div className="w-14 h-6 bg-muted/40 rounded-full animate-pulse" />
        </div>
      ))}
    </div>
  );
}

export function SessionListSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="p-3 rounded-xl bg-muted/30 space-y-2">
          <div className="flex items-center justify-between">
            <div className="h-3 w-16 bg-muted/50 rounded animate-pulse" />
            <div className="h-2.5 w-12 bg-muted/40 rounded animate-pulse" />
          </div>
          <div className="h-2.5 w-32 bg-muted/40 rounded animate-pulse" />
          <div className="h-2 w-24 bg-muted/30 rounded animate-pulse" />
        </div>
      ))}
    </div>
  );
}

export function CardSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="rounded-2xl bg-card border border-border p-4 space-y-3">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-3 bg-muted/50 rounded animate-pulse"
          style={{ width: `${100 - i * 15}%` }}
        />
      ))}
    </div>
  );
}
