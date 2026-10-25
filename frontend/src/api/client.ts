const API_URL = import.meta.env.VITE_API_URL || ''
export type Topic = { id: string; slug: string | null; name: string; description: string; estimated_minutes: number; content_url: string | null; module_id?: string | null; objectives?: string[]; difficulty?: string; review_status?: string; question_count?: number }
export type Lesson = Topic & { content: { explanation?: string; terminology?: { term: string; definition: string }[]; worked_examples?: { title: string; steps: string[]; takeaway: string }[]; exercises?: { prompt: string; success_criteria: string }[]; misconceptions?: { claim: string; correction: string }[]; mastery_criteria?: string[] }; prerequisites: Topic[] }
export type LibraryTrack = { id: string; title: string; description: string; modules: { id: string; title: string; description: string; topics: Topic[] }[] }
export type Edge = { id?: string; prerequisite_id: string; topic_id: string; confidence_score: number }
export type Question = { id: string; topic_id: string; prompt: string; choices: string[]; question_type?: string; difficulty?: number; learning_objective?: string }
export type Mastery = { topic_id: string; topic_name: string; p_mastery: number; last_updated: string; source: string }
export type RoadmapNode = { topic_id: string; topic_name: string; order: number; mastery_estimate: number; objective_breakdown: { mastery_deficit: number; retention_penalty: number; time_cost: number }; reason: string }
export type WeightedRoadmap = { mode: 'weighted'; path: RoadmapNode[]; computed_at: string }
export type ParetoPath = { label: string; path: RoadmapNode[]; objective_totals: { mastery_deficit: number; retention_penalty: number; time_cost: number } }
export type ParetoRoadmap = { mode: 'pareto'; paths: ParetoPath[]; computed_at: string }
export type Roadmap = WeightedRoadmap | ParetoRoadmap
export type EdgeReview = { edge_id: string; prerequisite_id: string; prerequisite_name: string; topic_id: string; topic_name: string; confidence_score: number; positive_gap: number; sample_count: number }
export type LabNode = { id: string; slug: string | null; name: string; description: string; module_id: string | null; module_name: string | null; track_id: string | null; track_name: string | null; difficulty: string; estimated_minutes: number; mastery_probability: number | null; mastery_observed: boolean; mastery_source: string | null; mastery_status: 'unknown' | 'unmastered' | 'partial' | 'mastered'; availability: 'available' | 'blocked' | 'unknown'; prerequisite_ids: string[]; dependent_ids: string[] }
export type LabGraph = { nodes: LabNode[]; edges: Edge[]; bkt_parameters: { p_init: number; p_transit: number; p_slip: number; p_guess: number }; diagnostics: { missing_edge_nodes: { prerequisite_id: string; topic_id: string }[]; is_dag: boolean; formal_knowledge_space_claim: false; note: string } }
export type BKTTrace = { prior_mastery: number; observed_response: 'correct' | 'incorrect'; probability_response_if_known: number; probability_response_if_unknown: number; weighted_known_likelihood: number; weighted_unknown_likelihood: number; observation_posterior: number; learning_transition: number; final_mastery: number; interpretation: string }
export type SearchEvent = { type: string; step?: number; current_node?: string; start_nodes?: string[]; target?: string; g?: number; h?: number; f?: number; selected?: string; target_reached?: boolean; search_path?: string[]; open_before?: { topic_id: string; f: number; g: number }[]; open_after?: { topic_id: string; f: number; g: number }[]; closed_before?: string[]; closed_after?: string[]; candidates?: { topic_id: string; eligible: boolean; reason?: string; g?: number; h?: number; f?: number }[]; message?: string }
export type LabSearch = { mode: string; start_topic_id: string | null; target_topic_id: string; final_roadmap_path: string[]; search_path: string[] | null; trace: SearchEvent[]; mastery: Record<string, number>; cost_weights: { mastery: number; retention: number; time: number }; heuristic: string; max_minutes_normalizer: number; persisted: false }
export type LabDemoResult = { mode: 'synthetic_integrated_demo'; persisted: false; parameters: LabGraph['bkt_parameters']; topic_id: string; assessment: { question_id: string; prompt: string; selected_choice_index: number; correct_choice_index: number; correct: boolean; explanation: string } | null; bkt: BKTTrace; synthetic_mastery: Record<string, number>; path_before: string[]; path_after: string[]; path_changed: boolean; target_topic_id: string; start_topic_id: string | null; search_path: string[] | null; a_star_trace: SearchEvent[]; explanation: string }

export function getToken() { return localStorage.getItem('orbit_token') }
export function setToken(token: string) { localStorage.setItem('orbit_token', token) }
export function clearToken() { localStorage.removeItem('orbit_token'); localStorage.removeItem('orbit_user_id') }

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${API_URL}${path}`, { ...options, headers })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body?.detail?.error?.message || body?.error?.message || `Request failed (${response.status})`)
  return body as T
}

export const auth = (kind: 'login' | 'signup', email: string, password: string) => api<{ user_id: string; token: string }>(`/api/v1/auth/${kind}`, { method: 'POST', body: JSON.stringify({ email, password }) })
export const getKst = () => api<{ topics: Topic[]; edges: Edge[] }>('/api/v1/kst')
export const getLabGraph = () => api<LabGraph>('/api/v1/ai-lab/graph')
export const labBktStep = (body: { prior_mastery: number; correct: boolean; p_transit?: number; p_slip?: number; p_guess?: number }) => api<{ mode: string; persisted: false; parameters: LabGraph['bkt_parameters']; trace: BKTTrace }>('/api/v1/ai-lab/bkt/step', { method: 'POST', body: JSON.stringify(body) })
export const labSearch = (body: { start_topic_id?: string | null; target_topic_id: string }) => api<LabSearch>('/api/v1/ai-lab/search', { method: 'POST', body: JSON.stringify(body) })
export const labDemoStep = (body: { topic_id: string; correct?: boolean; question_id?: string; selected_choice_index?: number; target_topic_id: string; start_topic_id?: string | null; mastery: Record<string, number> }) => api<LabDemoResult>('/api/v1/ai-lab/demo/step', { method: 'POST', body: JSON.stringify(body) })
export const getLibrary = () => api<{ tracks: LibraryTrack[] }>('/api/v1/content/library')
export const getLesson = (topicIdOrSlug: string) => api<Lesson>(`/api/v1/content/topics/${encodeURIComponent(topicIdOrSlug)}`)
export const getMastery = () => api<{ estimates: Mastery[] }>('/api/v1/mastery/me')
export const getRoadmap = (mode: 'weighted' | 'pareto' = 'weighted') => api<Roadmap>(`/api/v1/roadmap/me?mode=${mode}`)
export const getQuestions = (topicId?: string) => api<{ questions: Question[] }>(topicId ? `/api/v1/quiz/topic/${topicId}` : '/api/v1/quiz/diagnostic')
export const submitResponse = (question_id: string, selected_choice_index: number) => api<{ correct: boolean; correct_choice_index: number; explanation: string; distractor_explanations: { choice: string; feedback: string }[]; updated_mastery: { topic_id: string; p_mastery: number; source: string } }>('/api/v1/quiz/response', { method: 'POST', body: JSON.stringify({ question_id, selected_choice_index }) })
export const getEdgeReview = () => api<{ threshold: number; edges: EdgeReview[] }>('/api/v1/admin/edges/low-confidence')
export const refineEdges = () => api<{ updated_edges: number; edges: unknown[] }>('/api/v1/kst/edges/refine', { method: 'POST' })
