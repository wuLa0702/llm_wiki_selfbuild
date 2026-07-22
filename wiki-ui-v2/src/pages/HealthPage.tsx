import { useEffect, useState, useCallback, useRef } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import {
  Package, Timer, FileText, Network,
  ListTodo, Activity, AlertCircle, CheckCircle2, RefreshCw,
} from 'lucide-react';

interface HealthData {
  status: string;
  version?: string;
  uptime_seconds?: number;
  total_pages?: number;
  graph_nodes?: number;
  graph_edges?: number;
  ingest_queue_pending?: number;
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

interface MetricCardProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  sub?: string;
  variant?: 'default' | 'success' | 'warning' | 'error';
}

function MetricCard({ icon, label, value, sub, variant = 'default' }: MetricCardProps) {
  const borderColor = variant === 'success' ? 'border-l-green-500'
    : variant === 'warning' ? 'border-l-amber-500'
    : variant === 'error' ? 'border-l-red-500'
    : 'border-l-border';

  const iconColor = variant === 'success' ? 'text-green-500'
    : variant === 'warning' ? 'text-amber-500'
    : variant === 'error' ? 'text-red-500'
    : 'text-muted-foreground';

  return (
    <Card className={`border-l-3 ${borderColor} transition-shadow duration-150 hover:shadow-md`}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="text-2xl font-semibold tracking-tight">{value}</p>
            {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
          </div>
          <div className={`${iconColor} opacity-60`}>{icon}</div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function HealthPage() {
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');
  const [data, setData] = useState<HealthData | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const [refreshing, setRefreshing] = useState(false);
  // 用 ref 追踪 status，避免 fetchHealth 依赖 status 导致 effect 无限重跑
  const statusRef = useRef(status);
  statusRef.current = status;

  const fetchHealth = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const r = await fetch('/health');
      const d = await r.json();
      setData(d);
      setStatus(d.status === 'ok' ? 'ok' : 'error');
      if (d.status !== 'ok') setErrorMsg(d.message || '服务异常');
      else setErrorMsg('');
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (e: any) {
      // 仅在首次加载或手动刷新时显示错误，轮询静默失败
      if (statusRef.current === 'loading' || isManual) {
        setStatus('error');
        setErrorMsg(e.message || '无法连接服务');
      }
    } finally {
      if (isManual) setTimeout(() => setRefreshing(false), 400);
    }
  }, []);

  // 首次加载 + 10s 轮询（依赖空数组，只注册一次 interval）
  useEffect(() => {
    fetchHealth();
    const id = setInterval(() => fetchHealth(), 10_000);
    return () => clearInterval(id);
  }, [fetchHealth]);

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold mb-1">健康检查</h1>
            <p className="text-sm text-muted-foreground">系统运行状态和关键指标</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {lastUpdated && (
              <span className="text-[10px] text-muted-foreground/50">
                上次更新 {lastUpdated}
              </span>
            )}
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1.5 text-xs"
              onClick={() => fetchHealth(true)}
              disabled={refreshing}
            >
              <RefreshCw className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
              {refreshing ? '刷新中...' : '刷新'}
            </Button>
          </div>
        </div>

        {status === 'loading' ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1,2,3,4,5,6].map(i => (
              <Card key={i}>
                <CardContent className="p-4 space-y-2">
                  <Skeleton className="h-3 w-20" />
                  <Skeleton className="h-8 w-16" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : status === 'error' ? (
          <Card className="border-l-3 border-l-red-500">
            <CardContent className="p-6 flex items-center gap-4">
              <AlertCircle className="h-8 w-8 text-red-500 shrink-0" />
              <div>
                <p className="font-semibold text-destructive">服务异常</p>
                <p className="text-sm text-muted-foreground">{errorMsg}</p>
              </div>
            </CardContent>
          </Card>
        ) : (
          <>
            {/* Status banner */}
            <Card className="mb-6 border-l-3 border-l-green-500 bg-green-500/5">
              <CardContent className="p-4 flex items-center gap-3">
                <CheckCircle2 className="h-5 w-5 text-green-500" />
                <div>
                  <p className="text-sm font-medium text-green-600 dark:text-green-400">服务正常</p>
                  <p className="text-xs text-muted-foreground">所有系统正常运行</p>
                </div>
              </CardContent>
            </Card>

            {/* Metric cards grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <MetricCard
                icon={<Activity className="h-5 w-5" />}
                label="运行状态"
                value={data?.status === 'ok' ? '正常' : '异常'}
                variant={data?.status === 'ok' ? 'success' : 'error'}
              />

              <MetricCard
                icon={<Package className="h-5 w-5" />}
                label="服务版本"
                value={data?.version || '-'}
              />

              <MetricCard
                icon={<Timer className="h-5 w-5" />}
                label="运行时间"
                value={data?.uptime_seconds != null ? formatUptime(data.uptime_seconds) : '-'}
              />

              <MetricCard
                icon={<FileText className="h-5 w-5" />}
                label="Wiki 页面数"
                value={data?.total_pages ?? '-'}
              />

              <MetricCard
                icon={<Network className="h-5 w-5" />}
                label="图谱节点"
                value={data?.graph_nodes ?? '-'}
                sub={data?.graph_edges != null ? `${data.graph_edges} 条连接` : undefined}
              />

              <MetricCard
                icon={<ListTodo className="h-5 w-5" />}
                label="导入队列待处理"
                value={data?.ingest_queue_pending ?? '-'}
                variant={data?.ingest_queue_pending && data.ingest_queue_pending > 0 ? 'warning' : 'success'}
                sub={data?.ingest_queue_pending && data.ingest_queue_pending > 0 ? '等待处理中' : '队列为空'}
              />
            </div>

            {/* Raw data for debugging */}
            <details className="mt-6">
              <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
                原始响应数据
              </summary>
              <pre className="mt-2 text-xs bg-muted p-3 rounded-md overflow-x-auto border border-border">
                {JSON.stringify(data, null, 2)}
              </pre>
            </details>
          </>
        )}
      </div>
    </div>
  );
}
