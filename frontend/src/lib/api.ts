/** Same-origin client for the existing FastAPI endpoints. */
export type Role = 'warehouse' | 'authority'
export type Severity = 'critical' | 'at_risk' | 'surplus'
// Existing analytics payloads contain optional fields across artifact versions.
export interface ApiRecord { [key: string]: any }
export type HealthResponse = ApiRecord
export interface ForecastRun extends ApiRecord { products: ApiRecord[] }
export type HistoryPoint = ApiRecord
export interface LoadResult extends ApiRecord { validation:ValidationReport }
export interface UploadPreview extends ApiRecord { suggested_mapping: Record<string,{column:string|null;confidence:string}>; required_fields:string[]; optional_fields:string[]; columns:string[]; preview:Record<string,string>[]; validation:ValidationReport }
export interface ValidationReport extends ApiRecord { checks: ApiRecord[] }
export type NearestOption = ApiRecord
export interface TransfersResponse extends ApiRecord { suggestions: (ApiRecord & {donors: ApiRecord[]})[] }
export type AuthorityOverview = ApiRecord
export type AuthorityProduct = ApiRecord
export type AuthorityTransfer = ApiRecord
export interface ChatHistory extends ApiRecord { history:ChatTurn[]; suggested_questions:string[] }
export interface ChatTurn { role: string; content: string; at?: number }
export class ApiError extends Error {
 status: number; code: string; payload: unknown;
 constructor(status: number, payload: any) {
  const detail=payload?.detail ?? payload;
  super(typeof detail === 'string' ? detail : detail?.message ?? detail?.error ?? `Request failed (${status})`);
  this.status=status;this.payload=payload;this.code=detail?.error ?? '';
 }
}
export class SessionExpiredError extends ApiError {}
async function request<T = ApiRecord>(path: string, init?: RequestInit): Promise<T> {
 const response=await fetch('/api'+path,{credentials:'same-origin',...init});
 const payload=await response.json().catch(()=>({message:'The server returned an unreadable response.'}));
 if(!response.ok) throw response.status===410 ? new SessionExpiredError(response.status,payload) : new ApiError(response.status,payload);
 if(payload?.error) throw new ApiError(response.status,payload);
 return payload;
}
const post=<T=ApiRecord>(path:string,body:unknown={})=>request<T>(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export const api={
 health:()=>request<HealthResponse>('/health'),
 setSession:(role:Role)=>post('/session',{role}),
 endSession:()=>request('/session',{method:'DELETE'}),
 forecastResults:()=>request<ForecastRun>('/forecast/results'),
 runForecast:()=>post<ForecastRun>('/forecast/run'),
 uploadFile:(file:File)=>{const body=new FormData();body.append('file',file);return request<UploadPreview>('/upload',{method:'POST',body})},
 confirmUpload:(file:File,mapping:Record<string,string>,useCalculated:boolean)=>{const body=new FormData();body.append('file',file);body.append('mapping',JSON.stringify(mapping));body.append('use_calculated_closing',String(useCalculated));return request<LoadResult>('/upload/confirm',{method:'POST',body})},
 loadDemo:()=>post<LoadResult>('/demo/load'),
 products:()=>request<{products:{product_id:number;name:string}[]}>('/products'),
 templateUrl:'/api/upload/template',
 transfers:(distance=150)=>request<TransfersResponse>(`/transfers?max_distance_km=${distance}`),
 nearest:(product:number,quantity:number)=>request(`/transfers/nearest?product_id=${product}&quantity=${quantity}`),
 authorityOverview:()=>request<AuthorityOverview>('/authority/overview'),
 authorityProducts:(filter='all')=>request<{products:AuthorityProduct[]}>(`/authority/products?filter=${encodeURIComponent(filter)}`),
 authorityTransfers:(limit=30)=>request<{transfers:AuthorityTransfer[]}>(`/authority/transfers?limit=${limit}`),
 chatHistory:()=>request<ChatHistory>('/chat/history'),
 chat:(message:string)=>post('/chat',{message}),
};
