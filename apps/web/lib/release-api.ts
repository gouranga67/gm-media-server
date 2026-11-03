export type ReleaseObservation = {
  readonly id: string; readonly build_id: string; readonly check_key: string;
  readonly result: "pass" | "fail" | "not_applicable"; readonly note: string;
  readonly job_id: string | null; readonly edit_run_id: string | null;
  readonly publishing_post_id: string | null; readonly recorded_by: string; readonly created_at: string;
};
export type AcceptanceCheck = {
  readonly key: string; readonly label: string; readonly scope: "private" | "publishing";
  readonly evidence_kind: "edit" | "post" | "note" | "restore" | "reboot";
  readonly allow_na: boolean; readonly observation: ReleaseObservation | null;
};
export type ReleaseReadiness = {
  readonly version: number; readonly build_id: string; readonly generated_at: string; readonly schema_ready: boolean;
  readonly private_pilot_complete: boolean; readonly publishing_acceptance_complete: boolean;
  readonly public_customer_launch_ready: false; readonly automatic_model_calls: 0; readonly automatic_posts: 0;
  readonly checks: readonly AcceptanceCheck[];
  readonly technical: readonly { readonly key: string; readonly label: string; readonly status: "pass" | "pending";
    readonly scope: string; readonly detail?: string; readonly completed_at?: string | null; readonly method?: string }[];
  readonly queues: Readonly<Record<string, number>>;
  readonly history: readonly ReleaseObservation[];
  readonly playback_options: readonly { readonly job_id: string; readonly version: number; readonly project_name: string; readonly has_final: boolean }[];
  readonly published_posts: readonly { readonly id: string; readonly platform: string; readonly account_name: string;
    readonly schedule_requested: boolean | null; readonly publish_at: string; readonly version: number; readonly job_id: string }[];
};
export type ObservationInput = { readonly id: string; readonly build_id: string; readonly check_key: string;
  readonly result: ReleaseObservation["result"]; readonly note: string; readonly job_id: string | null;
  readonly version: number | null; readonly publishing_post_id: string | null; readonly observed: true };
async function call<T>(path: string, input?: ObservationInput): Promise<T> {
  const response = await fetch(`/api/media/release/${path}`, { method: input ? "POST" : "GET", cache: "no-store",
    headers: { "content-type": "application/json" }, body: input ? JSON.stringify(input) : undefined });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Release acceptance could not be saved. Check the fields and your owner access.");
  return data as T;
}
export const getReleaseReadiness = () => call<ReleaseReadiness>("readiness");
export const saveReleaseObservation = (input: ObservationInput) => call("acceptance", input);
