import {
  Box,
  ClipboardCheck,
  FolderKanban,
  LayoutDashboard,
  PlayCircle,
  Search,
  Settings,
  Shield,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

/**
 * 全局导航配置（interaction_flows.md §1.2 · 原型 v0.3 收编）。
 * 一级导航 10 项 IA 不变；P18 / P19 按里程碑隐藏（AppLayout 渲染层处理）。
 */
export interface NavLeaf {
  to: string;
  label: string;
  /** 页面编号注记（P02 等） */
  tag?: string;
}

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** 精确匹配，不做前缀高亮 */
  end?: boolean;
  badgeKey?: "approvals";
  children?: NavLeaf[];
}

/** 项目区子树依赖 :projectId；无 projectId 时全部回退 /projects（与原二级 Subnav 行为一致）。 */
export function buildNavTree(projectId: string | undefined): NavItem[] {
  const base = projectId ? `/projects/${projectId}` : "/projects";
  return [
    { to: "/", label: "工作台", icon: LayoutDashboard, end: true },
    {
      to: projectId ? `${base}/overview` : "/projects",
      label: "项目",
      icon: FolderKanban,
      children: [
        { to: projectId ? `${base}/overview` : "/projects", label: "总览", tag: "P02" },
        { to: `${base}/cases`, label: "用例", tag: "P05" },
        { to: `${base}/plans`, label: "计划", tag: "P06" },
        { to: `${base}/runs`, label: "执行（P09 项目过滤视图）", tag: "P09" },
        { to: `${base}/environments`, label: "环境（双入口同页）", tag: "P15" },
        { to: `${base}/integrations`, label: "集成", tag: "P03" },
        { to: `${base}/settings`, label: "设置", tag: "P04" },
      ],
    },
    {
      to: "/test-center/kickoff",
      label: "测试中心",
      icon: PlayCircle,
      children: [
        { to: "/test-center/kickoff", label: "发起执行", tag: "P08" },
        { to: "/test-center/runs", label: "TestRun 列表", tag: "P09" },
        { to: "/test-center/performance", label: "性能压测", tag: "P16" },
      ],
    },
    {
      to: "/gates/policies",
      label: "门禁",
      icon: Shield,
      children: [
        { to: "/gates/policies", label: "质量门禁策略", tag: "P11" },
        { to: "/gates/evaluations", label: "评估历史", tag: "P12" },
      ],
    },
    { to: "/releases", label: "发布", icon: Box },
    { to: "/approvals", label: "审批中心", icon: ClipboardCheck, badgeKey: "approvals" },
    { to: "/evidence", label: "证据", icon: Search },
    {
      to: "/admin/ai-cost",
      label: "管理后台",
      icon: Settings,
      children: [
        { to: "/admin/environments", label: "环境管理（组织级）", tag: "P15" },
        { to: "/admin/ai-cost", label: "AI 成本看板", tag: "P21" },
        { to: "/admin/model-routes", label: "模型路由", tag: "P22" },
        { to: "/admin/ai-switches", label: "AI 开关与降级", tag: "P23" },
        { to: "/admin/audit", label: "审计检索", tag: "P24" },
        { to: "/admin/integrations", label: "集成中心", tag: "P25" },
      ],
    },
  ];
}

export interface Crumb {
  label: string;
  to?: string;
}

/** 由 NavTree 配置按当前路径推导「分组 › 页面」两级面包屑；无命中返回空。 */
export function deriveBreadcrumb(pathname: string, tree: NavItem[]): Crumb[] {
  for (const item of tree) {
    const child = item.children?.find(
      (leaf) => pathname === leaf.to || pathname.startsWith(`${leaf.to}/`),
    );
    if (child) {
      return [
        { label: item.label, to: item.to },
        ...(child.label === item.label ? [] : [{ label: child.label }]),
      ];
    }
    const direct = item.end
      ? pathname === item.to
      : pathname === item.to || pathname.startsWith(`${item.to}/`);
    if (direct) {
      return [{ label: item.label, to: item.to }];
    }
  }
  return [];
}
