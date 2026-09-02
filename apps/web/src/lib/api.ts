import { mockDashboard } from '../data/mock';
import type {
  AuditEvent,
  DashboardData,
  EvidenceSignal,
  Incident,
  Metric,
  ProductField,
  ProposedAction,
  ReviewDecision,
  ReviewItem,
} from '../types';

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '/api/v1';
const REQUEST_TIMEOUT_MS = 2600;
const WEB_ACTOR = 'maya.chen@catalogops.demo';

interface RawMetricCounts {
  offers: number;
  predictions: number;
  pending_reviews: number;
  open_incidents: number;
}

interface RawMetricsSummary {
  window: string;
  dataset_label?: string;
  evidence_status?: string;
  evaluated_predictions: number;
  model_version: string;
  policy_label: string;
  precision: number;
  recall: number;
  f1: number;
  recall_at_5: number;
  mrr: number;
  ece: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  auto_match_rate: number;
  review_rate: number;
  no_match_rate: number;
  drift_status: 'stable' | 'warning' | 'critical';
  counts: RawMetricCounts;
  generated_at: string;
}

interface RawReview {
  id: string;
  offer_id: number;
  offer_title: string;
  candidate_product_id: string | null;
  candidate_title: string | null;
  confidence: number | null;
  status: 'pending' | 'resolved';
  priority: string;
  reason_codes: string[];
  assigned_to: string | null;
  resolution: string | null;
  resolved_product_id: string | null;
  notes: string | null;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

interface RawReviewList {
  items: RawReview[];
  total: number;
  pending: number;
  resolved: number;
  limit: number;
  offset: number;
}

interface RawIncident {
  id: string;
  title: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: string;
  metric_name: string;
  observed_value: number | null;
  expected_value: number | null;
  description: string;
  detected_at: string;
  resolved_at: string | null;
}

interface RawIncidentList { items: RawIncident[]; total: number }

interface RawInvestigation {
  id: string;
  incident_id: string;
  status: string;
  diagnosis: string;
  evidence: Array<Record<string, unknown>>;
  proposed_action: {
    type?: 'rollback_model' | 'adjust_threshold' | 'create_review_batch';
    parameters?: Record<string, unknown>;
    rationale?: string;
  };
  execution_result: Record<string, unknown> | null;
  requested_by: string;
  approved_by: string | null;
  approval_notes: string | null;
  executed_by: string | null;
  created_at: string;
  approved_at: string | null;
  executed_at: string | null;
}

interface RawInvestigationList { items: RawInvestigation[]; total: number }

interface RawAuditEvent {
  sequence: number;
  event_id: string;
  occurred_at: string;
  actor: string;
  role: string;
  action: string;
  resource_type: string;
  resource_id: string;
  payload: Record<string, unknown>;
  previous_hash: string;
  event_hash: string;
}

interface RawAuditList { items: RawAuditEvent[]; total: number; limit: number; offset: number }

interface RawAuditVerification {
  valid: boolean;
  checked_events: number;
  head_hash: string;
  broken_sequence: number | null;
}

function roleHeaders(role: 'reviewer' | 'operator' | 'admin'): Record<string, string> {
  return { 'X-Role': role, 'X-Actor': WEB_ACTOR };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...init?.headers,
      },
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`CatalogOps API returned ${response.status}`);
    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timeout);
  }
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function mapMetrics(summary: RawMetricsSummary): Metric[] {
  return [
    {
      label: 'Predictions evaluated',
      value: summary.counts.predictions.toLocaleString(),
      detail: summary.window,
      tone: 'neutral',
    },
    {
      label: 'Baseline precision',
      value: percent(summary.precision),
      detail: `${summary.evaluated_predictions.toLocaleString()} labeled predictions`,
      tone: summary.precision >= 0.95 ? 'good' : 'warning',
    },
    {
      label: 'Human review rate',
      value: percent(summary.review_rate),
      detail: `${summary.counts.pending_reviews.toLocaleString()} pending reviews`,
      tone: summary.review_rate <= 0.1 ? 'good' : 'warning',
    },
    {
      label: 'p95 inference latency',
      value: `${Math.round(summary.p95_latency_ms)} ms`,
      detail: `p50 ${Math.round(summary.p50_latency_ms)} ms`,
      tone: summary.p95_latency_ms < 250 ? 'good' : 'warning',
    },
  ];
}

function bandFor(score: number): ReviewItem['band'] {
  if (score >= 0.85) return 'high';
  if (score >= 0.55) return 'medium';
  return 'low';
}

function mapReview(review: RawReview): ReviewItem {
  const confidence = review.confidence ?? 0;
  const fields: ProductField[] = [
    {
      label: 'Raw title',
      listing: review.offer_title,
      candidate: review.candidate_title ?? 'No candidate title returned',
      status: review.candidate_title ? 'match' : 'missing',
    },
    {
      label: 'Product ID',
      listing: 'Not provided by seller',
      candidate: review.candidate_product_id ?? 'No canonical product',
      status: review.candidate_product_id ? 'missing' : 'conflict',
    },
  ];
  const signals: EvidenceSignal[] = [
    {
      label: 'Baseline score',
      value: 'Baseline model score reported by API',
      score: confidence,
      tone: confidence >= 0.55 ? 'positive' : 'negative',
    },
    {
      label: 'Policy route',
      value: bandFor(confidence) === 'medium' ? 'Inside human-review band' : `Classified ${bandFor(confidence)} confidence`,
      score: confidence,
      tone: 'neutral',
    },
  ];
  const created = new Date(review.created_at).getTime();
  const ageMinutes = Number.isFinite(created) ? Math.max(0, Math.round((Date.now() - created) / 60_000)) : 0;
  const decision: ReviewDecision = review.status === 'pending'
    ? 'pending'
    : review.resolution === 'matched'
      ? 'match'
      : review.resolution === 'no_match'
        ? 'no_match'
        : 'skipped';

  return {
    id: review.id,
    listingId: `OFFER-${review.offer_id}`,
    seller: review.assigned_to ? `Assigned to ${review.assigned_to}` : 'Live API catalog',
    marketplace: 'API',
    listingTitle: review.offer_title,
    canonicalId: review.candidate_product_id ?? 'NO-CANDIDATE',
    canonicalTitle: review.candidate_title ?? 'No canonical candidate',
    confidence,
    band: bandFor(confidence),
    ageMinutes,
    decision,
    reason: review.reason_codes.length
      ? review.reason_codes.map((code) => code.replaceAll('_', ' ')).join(' · ')
      : 'Routed by the configurable confidence policy.',
    fields,
    signals,
  };
}

function actionType(rawType: string | undefined): ProposedAction['type'] {
  if (rawType === 'rollback_model') return 'rollback';
  if (rawType === 'create_review_batch') return 'review_batch';
  return 'threshold';
}

function mapProposedAction(investigation: RawInvestigation): ProposedAction {
  const type = actionType(investigation.proposed_action.type);
  const parameters = investigation.proposed_action.parameters ?? {};
  const label = type === 'rollback'
    ? `Rollback model to ${String(parameters.target_version ?? 'previous version')}`
    : type === 'review_batch'
      ? 'Create targeted review batch'
      : 'Adjust matching thresholds';
  return {
    id: investigation.id,
    type,
    label,
    description: investigation.proposed_action.rationale ?? `Bounded ${type.replace('_', ' ')} action proposed by the live investigation.`,
    impact: type === 'threshold'
      ? `auto ${String(parameters.auto_match ?? 0.89)} · review ${String(parameters.review ?? 0.55)}`
      : type === 'review_batch'
        ? `up to ${String(parameters.limit ?? 25)} records`
        : 'restores previous registered model',
    reversible: type !== 'review_batch',
    selected: true,
  };
}

function displayMetric(value: number | null, metricName: string): string {
  if (value === null) return '—';
  return /rate|precision|recall|error|ece/i.test(metricName) ? `${(value * 100).toFixed(1)}%` : String(value);
}

function mapIncident(raw: RawIncident, investigations: RawInvestigation[]): Incident {
  const investigation = investigations.find((item) => item.incident_id === raw.id && item.status !== 'rejected');
  const status: Incident['status'] = raw.status === 'resolved' || investigation?.status === 'executed'
    ? 'resolved'
    : investigation?.status === 'approved'
      ? 'approved'
      : investigation?.status === 'proposed'
        ? 'awaiting_approval'
        : 'investigating';
  const evidenceFindings = investigation?.evidence.slice(0, 4).map((item) => {
    const source = String(item.source ?? 'evidence').replaceAll('_', ' ');
    const rest = Object.entries(item)
      .filter(([key]) => key !== 'source')
      .map(([key, value]) => `${key.replaceAll('_', ' ')}: ${String(value)}`)
      .join(' · ');
    return `${source}: ${rest}`;
  }) ?? [];
  return {
    id: raw.id,
    investigationId: investigation?.id,
    title: raw.title,
    severity: raw.severity,
    status,
    startedAt: raw.detected_at,
    owner: investigation ? `Requested by ${investigation.requested_by}` : 'Unassigned',
    metric: raw.metric_name,
    currentValue: displayMetric(raw.observed_value, raw.metric_name),
    baselineValue: displayMetric(raw.expected_value, raw.metric_name),
    affectedRecords: 0,
    summary: investigation?.diagnosis ?? raw.description,
    findings: evidenceFindings.length ? evidenceFindings : ['No investigation evidence has been recorded yet.'],
    proposedActions: investigation ? [mapProposedAction(investigation)] : [{
      id: `draft-${raw.id}`,
      type: 'review_batch',
      label: 'Create targeted review batch',
      description: 'Route the highest-disagreement records for bounded human labeling before changing the model.',
      impact: 'up to 25 records · no production policy change',
      reversible: false,
      selected: true,
    }],
  };
}

function mapAudit(event: RawAuditEvent): AuditEvent {
  const actorLower = event.actor.toLowerCase();
  const actorType: AuditEvent['actorType'] = event.role === 'reviewer'
    ? 'human'
    : /agent|monitor|ci|system/.test(actorLower)
      ? 'agent'
      : 'human';
  const outcome: AuditEvent['outcome'] = /blocked|rejected/.test(event.action)
    ? 'blocked'
    : /proposed|created/.test(event.action)
      ? 'pending'
      : 'success';
  return {
    id: event.event_id,
    timestamp: event.occurred_at,
    actor: event.actor,
    actorType,
    action: event.action.replaceAll('.', '_').toUpperCase(),
    target: `${event.resource_type} / ${event.resource_id}`,
    detail: Object.entries(event.payload)
      .map(([key, value]) => `${key.replaceAll('_', ' ')}: ${typeof value === 'object' ? JSON.stringify(value) : String(value)}`)
      .join(' · '),
    outcome,
    hash: `sha256:${event.event_hash.slice(0, 8)}…${event.event_hash.slice(-4)}`,
  };
}

export async function getDashboard(): Promise<DashboardData> {
  const [summary, reviewList, incidentList, investigationList, auditList, auditVerification] = await Promise.all([
    request<RawMetricsSummary>('/metrics/summary'),
    request<RawReviewList>('/reviews?limit=50'),
    request<RawIncidentList>('/incidents'),
    request<RawInvestigationList>('/investigations', { headers: roleHeaders('operator') }),
    request<RawAuditList>('/audit?limit=100', { headers: roleHeaders('operator') }),
    request<RawAuditVerification>('/audit/verify', { headers: roleHeaders('operator') }),
  ]);
  const mappedReviews = reviewList.items.map(mapReview);
  const mappedIncidents = incidentList.items.map((incident) => mapIncident(incident, investigationList.items));
  const mappedAudit = auditList.items.map(mapAudit);
  return {
    ...mockDashboard,
    modelVersion: summary.model_version,
    datasetLabel: summary.dataset_label ?? 'Connected API evidence',
    lastUpdated: summary.generated_at,
    pipeline: {
      recallAtK: percent(summary.recall_at_5),
      precision: percent(summary.precision),
      reviewRate: percent(summary.review_rate),
      decisionCoverage: percent(summary.auto_match_rate + summary.review_rate + summary.no_match_rate),
    },
    auditIntegrity: {
      status: auditVerification.valid ? 'verified' : 'invalid',
      checkedEvents: auditVerification.checked_events,
      headHash: auditVerification.head_hash,
    },
    metrics: mapMetrics(summary),
    // The summary endpoint has no time-series payload; this remains an explicitly labeled UI fixture.
    chart: mockDashboard.chart,
    reviews: mappedReviews,
    incidents: mappedIncidents,
    audit: mappedAudit,
  };
}

export async function submitReviewDecision(item: ReviewItem, decision: ReviewDecision): Promise<void> {
  const resolution = decision === 'match' ? 'matched' : decision === 'no_match' ? 'no_match' : 'needs_more_information';
  await request(`/reviews/${encodeURIComponent(item.id)}/resolve`, {
    method: 'POST',
    headers: roleHeaders('reviewer'),
    body: JSON.stringify({
      resolution,
      ...(decision === 'match' ? { resolved_product_id: item.canonicalId } : {}),
      notes: 'Resolved from the CatalogOps review workspace.',
    }),
  });
}

function rawAction(action: ProposedAction): RawInvestigation['proposed_action'] {
  if (action.type === 'rollback') {
    return { type: 'rollback_model', parameters: { target_version: 'catalogops-lexical-v0' }, rationale: action.description };
  }
  if (action.type === 'review_batch') {
    return { type: 'create_review_batch', parameters: { limit: 25, metric_slice: 'quality_alert' }, rationale: action.description };
  }
  return { type: 'adjust_threshold', parameters: { auto_match: 0.89, review: 0.55 }, rationale: action.description };
}

export async function runInvestigation(incidentId: string, action?: ProposedAction): Promise<RawInvestigation> {
  return request('/investigations/run', {
    method: 'POST',
    headers: roleHeaders('operator'),
    body: JSON.stringify({ incident_id: incidentId, ...(action ? { proposed_action: rawAction(action) } : {}) }),
  });
}

export async function approveInvestigationAction(investigationId: string, action: ProposedAction): Promise<void> {
  await request(`/investigations/${encodeURIComponent(investigationId)}/approve`, {
    method: 'POST',
    headers: roleHeaders('admin'),
    body: JSON.stringify({ notes: `Approved from web console: ${action.label}` }),
  });
}

export async function executeInvestigationAction(investigationId: string): Promise<void> {
  await request(`/investigations/${encodeURIComponent(investigationId)}/execute`, {
    method: 'POST',
    headers: roleHeaders('operator'),
    body: JSON.stringify({ dry_run: false }),
  });
}

export interface MatchPredictionInput {
  title: string;
  brand?: string;
  mpn?: string;
  gtin?: string;
  top_k?: number;
  persist?: boolean;
}

export interface MatchPrediction {
  prediction_id: string | null;
  offer_id: number | null;
  confidence: number;
  decision: 'auto_match' | 'review' | 'no_match';
  candidates: Array<{ product_id: string; title: string; brand: string | null; score: number; evidence: string[] }>;
  evidence: string[];
  model_version: string;
  latency_ms: number;
  thresholds: Record<string, number>;
}

export async function predictMatch(input: MatchPredictionInput): Promise<MatchPrediction> {
  return request('/matches/predict', {
    method: 'POST',
    headers: { 'X-Actor': WEB_ACTOR },
    body: JSON.stringify(input),
  });
}
