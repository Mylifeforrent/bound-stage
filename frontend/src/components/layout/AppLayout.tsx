import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  ChevronRight,
  LogOut,
  Menu,
} from "lucide-react";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import type { ResourceEnvelope } from "@/api/types";
import { ApiError, isUndeveloped } from "@/api/errors";
import { logoutSession } from "@/api/session";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SessionReauthNotice } from "@/components/layout/SessionReauthNotice";
import { AiDegradeBanner } from "@/components/domain/AiDegradeBanner";
import { buildNavTree, deriveBreadcrumb } from "@/components/layout/navTree";
import { useReauthRequired, useSession } from "@/hooks/useSession";
import { ViewportProvider, useViewport } from "@/hooks/useViewport";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/uiStore";

export function AppLayout() {
  return (
    <ViewportProvider>
      <AppShell />
    </ViewportProvider>
  );
}

function AppShell() {
  const { projectId } = useParams();
  const location = useLocation();
  const queryClient = useQueryClient();
  const collapsed = useUiStore((state) => state.sidebarCollapsed);
  const toggle = useUiStore((state) => state.toggleSidebar);
  const viewport = useViewport();
  const session = useSession();
  const iconOnly = viewport.sidebarIconOnly || collapsed;
  const tree = useMemo(() => buildNavTree(projectId), [projectId]);
  const crumbs = deriveBreadcrumb(location.pathname, tree);

  /* 树节点开合状态：进入分组时自动展开，可手动收起 */
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  useEffect(() => {
    if (iconOnly || crumbs.length === 0) {
      return;
    }
    setOpenGroups((prev) => (prev[crumbs[0].label] ? prev : { ...prev, [crumbs[0].label]: true }));
    // crumbs[0].label 随 pathname 变化，直接依赖 pathname 更直观
  }, [location.pathname, iconOnly]);

  const toggleGroup = (label: string) => {
    setOpenGroups((prev) => ({ ...prev, [label]: !prev[label] }));
  };

  const badgeQuery = useQuery({
    queryKey: queryKeys.notificationsBadge,
    queryFn: () =>
      api.get<ResourceEnvelope<{ unread_count?: number }>>("API-022", "/api/v1/notifications/badge"),
  });
  const orgQuery = useQuery({
    queryKey: queryKeys.organization,
    queryFn: () => api.get<ResourceEnvelope<Record<string, unknown>>>("API-010", "/api/v1/organizations/current"),
  });

  const unread = badgeQuery.data?.data.unread_count;
  const showCount = typeof unread === "number" && unread > 0;
  const badgeUndeveloped = isUndeveloped(badgeQuery.error);
  const banner = aiBanner(orgQuery.data?.data, orgQuery.error, orgQuery.isPending);
  const reauthRequired = useReauthRequired();
  const orgName = session.me?.organization.name;
  const userName = session.me?.user.display_name;

  return (
    <TooltipProvider>
      <div className="flex h-full bg-background">
        <aside
          className={cn(
            "flex h-full flex-col border-r border-sidebar-accent bg-sidebar text-sidebar-foreground transition-[width] duration-200",
            iconOnly ? "w-16" : "w-56",
          )}
        >
          <div className="flex items-center gap-2 border-b border-sidebar-accent px-3 py-4">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-sidebar-primary text-sm font-bold text-primary-foreground">
              H
            </div>
            {iconOnly ? null : (
              <span className="min-w-0 text-sm font-semibold text-white">
                HuntAI Test
                <span className="block text-[10px] font-normal text-sidebar-foreground/40">
                  企业内部 AI 测试平台
                </span>
              </span>
            )}
          </div>
          <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-2 py-2" aria-label="一级导航">
            {tree.map((item) => {
              const groupActive = crumbs.length > 0 && crumbs[0].label === item.label;
              if (item.children && !iconOnly) {
                return (
                  <div key={`${item.label}:${item.to}`} className="flex flex-col">
                    <div
                      className={cn(
                        "flex items-center rounded-md transition-colors",
                        groupActive
                          ? "bg-sidebar-accent text-white shadow-[inset_2px_0_0_0_var(--color-sidebar-primary)]"
                          : "text-sidebar-foreground hover:bg-sidebar-accent/70 hover:text-white",
                      )}
                    >
                      <NavLink
                        to={item.to}
                        end={false}
                        className="flex min-w-0 flex-1 items-center gap-2.5 px-2.5 py-2 text-sm"
                      >
                        <item.icon className="size-4 shrink-0" />
                        <span className="flex-1 truncate">{item.label}</span>
                      </NavLink>
                      <button
                        type="button"
                        onClick={() => toggleGroup(item.label)}
                        aria-expanded={!!openGroups[item.label]}
                        aria-label={`展开/收起 ${item.label}`}
                        className="px-1.5 py-2.5 text-sidebar-foreground/60 hover:text-white"
                      >
                        <ChevronRight
                          className={cn("size-4 transition-transform", openGroups[item.label] && "rotate-90")}
                        />
                      </button>
                    </div>
                    {openGroups[item.label] ? (
                      <div className="ml-2.5 flex flex-col border-l border-sidebar-accent py-0.5 pl-1.5">
                        {item.children.map((leaf) => (
                          <NavLink
                            key={`${leaf.tag ?? ""}:${leaf.to}:${leaf.label}`}
                            to={leaf.to}
                            end={false}
                            className={({ isActive }) =>
                              cn(
                                "relative flex items-center rounded-md px-2.5 py-1.5 text-xs transition-colors",
                                isActive
                                  ? "bg-sidebar-accent font-medium text-white"
                                  : "text-sidebar-foreground/80 hover:bg-sidebar-accent/70 hover:text-white",
                              )
                            }
                          >
                            <span className="truncate">{leaf.label}</span>
                            {leaf.tag ? (
                              <span className="ml-auto pl-2 text-[9px] text-sidebar-foreground/40">{leaf.tag}</span>
                            ) : null}
                          </NavLink>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              }
              return (
                <NavLink
                  key={`${item.label}:${item.to}`}
                  to={item.to}
                  end={"end" in item ? item.end : false}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
                      iconOnly && "justify-center px-0",
                      groupActive || isActive
                        ? "bg-sidebar-accent font-medium text-white shadow-[inset_2px_0_0_0_var(--color-sidebar-primary)]"
                        : "text-sidebar-foreground hover:bg-sidebar-accent/70 hover:text-white",
                    )
                  }
                >
                  <item.icon className="size-4 shrink-0" />
                  {iconOnly ? null : <span className="flex-1">{item.label}</span>}
                  {!iconOnly && "badgeKey" in item ? (
                    showCount ? (
                      <Badge variant="destructive" className="border-transparent px-1.5 py-0 text-[10px]">
                        {unread}
                      </Badge>
                    ) : badgeUndeveloped ? (
                      <span className="text-[9px] text-sidebar-foreground/50">未开发</span>
                    ) : null
                  ) : null}
                </NavLink>
              );
            })}
          </nav>
          {iconOnly ? null : (
            <p className="px-3 py-3 text-[10px] leading-relaxed text-sidebar-foreground/40">
              助手 / 技能入口按里程碑隐藏
            </p>
          )}
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-12 items-center gap-3 border-b bg-card px-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={toggle}
              aria-label="折叠侧栏"
              disabled={viewport.sidebarIconOnly}
            >
              <Menu className="size-4" />
            </Button>
            <nav aria-label="面包屑" className="flex min-w-0 flex-none items-center gap-1.5 text-sm">
              {crumbs.length === 0 ? null : crumbs.map((crumb, index) => (
                <span key={`${crumb.label}:${index}`} className="flex items-center gap-1.5">
                  {index > 0 ? <ChevronRight className="size-3 text-muted-foreground/60" /> : null}
                  {index === crumbs.length - 1 ? (
                    <span className="font-semibold">{crumb.label}</span>
                  ) : crumb.to ? (
                    <NavLink to={crumb.to} className="text-xs text-muted-foreground hover:text-foreground">
                      {crumb.label}
                    </NavLink>
                  ) : (
                    <span className="text-xs text-muted-foreground">{crumb.label}</span>
                  )}
                </span>
              ))}
            </nav>
            <div className="min-w-0 flex-1">
              {orgName || userName ? (
                <p className="truncate text-right text-xs text-muted-foreground lg:text-left">
                  {orgName ?? "组织"}
                  {userName ? ` · ${userName}` : ""}
                </p>
              ) : null}
            </div>
            {banner.tone === "pending" ? (
              <div className="hidden items-center gap-2 rounded-md border border-warning/30 bg-warning-foreground px-2.5 py-1 text-xs text-warning sm:flex">
                <span className="size-1.5 rounded-full bg-warning" />
                {banner.text}
              </div>
            ) : null}
            <Button variant="ghost" size="icon" aria-label="通知（缺口 G4，非命令通道）">
              <Bell className="size-4" />
            </Button>
            {badgeUndeveloped ? (
              <span className="hidden text-[10px] text-muted-foreground lg:inline">通知未开发</span>
            ) : null}
            <Button
              variant="ghost"
              size="icon"
              aria-label="退出登录"
              onClick={() => {
                void logoutSession(queryClient);
              }}
            >
              <LogOut className="size-4" />
            </Button>
          </header>
          {banner.tone === "warn" ? (
            <div className="border-b bg-card px-4 py-2">
              <AiDegradeBanner active scope={banner.text} />
            </div>
          ) : null}
          {viewport.mode === "readonly" ? (
            <div className="border-b border-warning/30 bg-warning-foreground px-4 py-2 text-xs text-warning">
              当前宽度 &lt; 1024px，仅只读浏览。批准、发起执行与终止请在桌面（≥1024px）操作。
            </div>
          ) : null}
          {reauthRequired ? (
            <div className="border-b bg-card px-4 py-2">
              <SessionReauthNotice active />
            </div>
          ) : null}
          <main className={cn("flex-1 overflow-y-auto", viewport.mode === "desktop" ? "p-6" : "p-4")}>
            <div className="mx-auto flex max-w-7xl flex-col gap-6">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}

function aiBanner(
  data: Record<string, unknown> | undefined,
  error: unknown,
  pending: boolean,
): { tone: "ok" | "warn" | "pending"; text: string } {
  if (pending) {
    return { tone: "pending", text: "加载组织信息…" };
  }
  if (error instanceof ApiError && error.kind === "permission") {
    return { tone: "pending", text: "无组织访问权限" };
  }
  if (error || !data) {
    if (isUndeveloped(error)) {
      return { tone: "pending", text: "待 API-010" };
    }
    return { tone: "pending", text: "组织信息不可用" };
  }
  const controls = asRecord(data.capability_controls);
  if (controls.ai_global_tightened === true) {
    return { tone: "warn", text: "全局 AI 已关停" };
  }
  const caps = Array.isArray(controls.tightened_capabilities) ? controls.tightened_capabilities : [];
  const mods = Array.isArray(controls.tightened_modules) ? controls.tightened_modules : [];
  if (caps.length > 0 || mods.length > 0) {
    const scope = typeof controls.banner_scope === "string" ? controls.banner_scope : "AI 降级中";
    return { tone: "warn", text: scope };
  }
  return { tone: "ok", text: "AI 正常运行中" };
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
