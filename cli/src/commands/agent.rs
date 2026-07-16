//! OKX Agent Identity — ERC-8004 on-chain agent identity on X Layer.
//!
//! Implements the `onchainos agent ...` command family consumed by the
//! `okx-agent-identity` skill (v4.0.1): register / update / list / search
//! agents, manage their listing state, upload avatars, and read reviews.
//!
//! ## Backend endpoints — INFERRED, verify before relying on live calls
//!
//! The ERC-8004 agent-identity backend contract is **not** published in this
//! repository (no OpenAPI spec, no prior source, GitHub release access is not
//! available in this environment). The endpoint paths below follow the
//! established agentic convention observed in `competition.rs`:
//!   * public reads  → `/priapi/v1/dapp/agentic/agent/*`
//!   * authed writes → `/priapi/v5/wallet/agentic/agent/*` (Bearer + project header)
//!
//! Everything that does NOT depend on the backend works today and is unit
//! tested: the full command tree, `--service` JSON parsing, role / fee /
//! serviceType / endpoint / avatar / service-required validation (matching the
//! skill's `errors.md` bail strings), the local `validate-listing` QA pass, and
//! the label / fee-display enrichment helpers. When the real endpoint paths and
//! request/response field names are confirmed, only the `EP_*` constants and the
//! request/response field mapping in each network fn need adjustment.

use anyhow::{bail, Result};
use base64::Engine;
use clap::Subcommand;
use serde_json::{json, Value};

use super::Context;
use crate::client::ApiClient;
use crate::output;
use crate::wallet_store;

// ── INFERRED endpoints (see module doc) ───────────────────────────────
const EP_PRECHECK: &str = "/priapi/v5/wallet/agentic/agent/preCheck";
const EP_CREATE: &str = "/priapi/v5/wallet/agentic/agent/create";
const EP_UPDATE: &str = "/priapi/v5/wallet/agentic/agent/update";
const EP_ACTIVATE: &str = "/priapi/v5/wallet/agentic/agent/activate";
const EP_DEACTIVATE: &str = "/priapi/v5/wallet/agentic/agent/deactivate";
const EP_UPLOAD: &str = "/priapi/v5/wallet/agentic/agent/upload";
const EP_MY_AGENTS: &str = "/priapi/v5/wallet/agentic/agent/myAgents";
const EP_FEEDBACK_SUBMIT: &str = "/priapi/v5/wallet/agentic/agent/feedback/submit";
const EP_DETAIL: &str = "/priapi/v1/dapp/agentic/agent/detail";
const EP_SEARCH: &str = "/priapi/v1/dapp/agentic/agent/search";
const EP_SERVICE_LIST: &str = "/priapi/v1/dapp/agentic/agent/serviceList";
const EP_FEEDBACK_LIST: &str = "/priapi/v1/dapp/agentic/agent/feedback/list";

/// Agentic project header — mirrors the value used by `competition.rs` for the
/// `/priapi/v5/wallet/agentic/*` family. Inferred to apply to agent identity
/// too; adjust if the backend expects a different project id.
const PROJECT_HEADER: &str = "4d156bf0c61130f2692d097ecb68dbe4";

/// Max avatar upload size (bytes). The skill re-asks for a smaller file above
/// this; the CLI is the authoritative gate.
const MAX_AVATAR_BYTES: usize = 1024 * 1024;

#[derive(Subcommand)]
pub enum AgentCommand {
    /// Pre-registration gate: folds first-time consent + per-wallet uniqueness.
    /// Returns { canCreate, role, reason?, consent?, existingSameRole, aspCount }.
    PreCheck {
        /// Role: user | asp | evaluator
        #[arg(long)]
        role: String,
        /// Consent key (UUID) returned by a prior pre-check consent prompt
        #[arg(long)]
        consent_key: Option<String>,
    },
    /// Register a new agent identity (user / asp / evaluator).
    Create {
        /// Role: user | asp | evaluator
        #[arg(long)]
        role: String,
        /// Agent (brand) name
        #[arg(long)]
        name: String,
        /// Agent description (top-level; empty string allowed for user/evaluator)
        #[arg(long, default_value = "")]
        description: String,
        /// Avatar CDN URL (from `agent upload`). Required for ASP.
        #[arg(long)]
        picture: Option<String>,
        /// Services JSON array. Required (non-empty) for ASP.
        #[arg(long)]
        service: Option<String>,
    },
    /// Update an existing agent identity.
    Update {
        /// Target agent id
        #[arg(long)]
        agent_id: String,
        /// New name
        #[arg(long)]
        name: Option<String>,
        /// New description
        #[arg(long)]
        description: Option<String>,
        /// New avatar CDN URL (from `agent upload`)
        #[arg(long)]
        picture: Option<String>,
        /// Services JSON array with per-element `operation` (create/update/delete)
        #[arg(long)]
        service: Option<String>,
    },
    /// Local listing QA (name/service/fee/type/endpoint). Returns { pass, findings[] }.
    /// Runs entirely offline — no network call.
    ValidateListing {
        /// Role: user | asp | evaluator
        #[arg(long)]
        role: String,
        /// Agent name
        #[arg(long)]
        name: String,
        /// Agent description
        #[arg(long, default_value = "")]
        description: String,
        /// Services JSON array (asp)
        #[arg(long)]
        service: Option<String>,
    },
    /// List agents owned by the logged-in wallet.
    GetMyAgents,
    /// Fetch one or more agents by id (comma-separated).
    GetAgents {
        /// Agent ids, comma-separated (e.g. `42,58`)
        #[arg(long)]
        agent_ids: String,
    },
    /// Hidden dual-mode read alias: with --agent-ids → detail, else → my agents.
    #[command(hide = true)]
    Get {
        #[arg(long)]
        agent_ids: Option<String>,
    },
    /// Publish (activate) an agent listing.
    Activate {
        #[arg(long)]
        agent_id: String,
        /// Preferred language (BCP-47, e.g. zh-CN / en-US) — required by backend
        #[arg(long)]
        preferred_language: String,
    },
    /// Unpublish (deactivate) an agent listing.
    Deactivate {
        #[arg(long)]
        agent_id: String,
    },
    /// Upload an avatar image; returns { url } for use as --picture.
    Upload {
        /// Path to a local image file (PNG/JPEG/WebP, ≤1 MB)
        #[arg(long)]
        file: String,
    },
    /// Search the agent marketplace.
    Search {
        /// Full user utterance (verbatim), #id tokens stripped by caller
        #[arg(long)]
        query: String,
        /// Rating-related filter wording
        #[arg(long)]
        feedback: Option<String>,
        /// Domain/keyword filter wording
        #[arg(long)]
        agent_info: Option<String>,
        /// Status filter (verbatim; never defaulted)
        #[arg(long)]
        status: Option<String>,
        /// Service interface-token filter
        #[arg(long)]
        service: Option<String>,
        /// Page number (1-based)
        #[arg(long, default_value = "1")]
        page: u32,
    },
    /// List the services offered by an agent.
    ServiceList {
        #[arg(long)]
        agent_id: String,
    },
    /// Submit a review for an agent.
    FeedbackSubmit {
        #[arg(long)]
        agent_id: String,
        /// Rating value (backend scale)
        #[arg(long)]
        rating: i64,
        /// Free-text review
        #[arg(long, default_value = "")]
        description: String,
    },
    /// List reviews for an agent.
    FeedbackList {
        #[arg(long)]
        agent_id: String,
        #[arg(long, default_value = "1")]
        page: u32,
    },
}

pub async fn execute(ctx: &Context, command: AgentCommand) -> Result<()> {
    let data = match command {
        AgentCommand::PreCheck { role, consent_key } => {
            pre_check(&role, consent_key.as_deref()).await?
        }
        AgentCommand::Create {
            role,
            name,
            description,
            picture,
            service,
        } => create(&role, &name, &description, picture.as_deref(), service.as_deref()).await?,
        AgentCommand::Update {
            agent_id,
            name,
            description,
            picture,
            service,
        } => {
            update(
                &agent_id,
                name.as_deref(),
                description.as_deref(),
                picture.as_deref(),
                service.as_deref(),
            )
            .await?
        }
        AgentCommand::ValidateListing {
            role,
            name,
            description,
            service,
        } => validate_listing(&role, &name, &description, service.as_deref())?,
        AgentCommand::GetMyAgents => get_my_agents().await?,
        AgentCommand::GetAgents { agent_ids } => get_agents(ctx, &agent_ids).await?,
        AgentCommand::Get { agent_ids } => match agent_ids {
            Some(ids) => get_agents(ctx, &ids).await?,
            None => get_my_agents().await?,
        },
        AgentCommand::Activate {
            agent_id,
            preferred_language,
        } => activate(&agent_id, &preferred_language).await?,
        AgentCommand::Deactivate { agent_id } => deactivate(&agent_id).await?,
        AgentCommand::Upload { file } => upload(&file).await?,
        AgentCommand::Search {
            query,
            feedback,
            agent_info,
            status,
            service,
            page,
        } => {
            search(
                ctx,
                &query,
                feedback.as_deref(),
                agent_info.as_deref(),
                status.as_deref(),
                service.as_deref(),
                page,
            )
            .await?
        }
        AgentCommand::ServiceList { agent_id } => service_list(ctx, &agent_id).await?,
        AgentCommand::FeedbackSubmit {
            agent_id,
            rating,
            description,
        } => feedback_submit(&agent_id, rating, &description).await?,
        AgentCommand::FeedbackList { agent_id, page } => {
            feedback_list(ctx, &agent_id, page).await?
        }
    };
    output::success(data);
    Ok(())
}

// ── Role ───────────────────────────────────────────────────────────────

/// Canonicalize / validate `--role`. The CLI is strict: only `user` / `asp` /
/// `evaluator` (the skill maps synonyms & numbers before calling).
fn parse_role(role: &str) -> Result<&'static str> {
    match role.trim().to_lowercase().as_str() {
        "user" => Ok("user"),
        "asp" => Ok("asp"),
        "evaluator" => Ok("evaluator"),
        _ => bail!("invalid value for --role"),
    }
}

/// English-canonical role label (the skill translates `*Label` fields).
fn role_label(role: &str) -> &'static str {
    match role.trim().to_lowercase().as_str() {
        "user" => "User",
        "asp" => "ASP",
        "evaluator" => "Evaluator",
        _ => "",
    }
}

/// Localized-neutral service-type label. A2MCP = API service, A2A = agent to agent.
fn service_type_label(raw: &str) -> &'static str {
    match raw.trim().to_uppercase().as_str() {
        "A2MCP" => "API service",
        "A2A" => "agent to agent",
        _ => "",
    }
}

/// Fee display string per invariants.md §Fee.
/// Non-empty fee → `<N> USDT`; empty A2MCP → `free`; empty A2A → `negotiable`.
fn fee_display(fee: &str, service_type: &str) -> String {
    let fee = fee.trim();
    if !fee.is_empty() {
        return format!("{fee} USDT");
    }
    match service_type.trim().to_uppercase().as_str() {
        "A2A" => "negotiable".to_string(),
        _ => "free".to_string(),
    }
}

// ── Service JSON ────────────────────────────────────────────────────────

/// Parse the `--service` JSON array into a Vec of objects, preserving unknown
/// keys so they pass through to the backend untouched.
fn parse_services(service: Option<&str>) -> Result<Vec<Value>> {
    let Some(raw) = service else {
        return Ok(Vec::new());
    };
    let raw = raw.trim();
    if raw.is_empty() {
        return Ok(Vec::new());
    }
    let parsed: Value = serde_json::from_str(raw)
        .map_err(|e| anyhow::anyhow!("invalid --service JSON: {e}"))?;
    match parsed {
        Value::Array(a) => Ok(a),
        // Tolerate a single service object (not wrapped in an array).
        Value::Object(_) => Ok(vec![parsed]),
        _ => bail!("invalid --service JSON: expected an array of service objects"),
    }
}

/// True when the fee is a plain decimal number with ≤6 dp and no currency /
/// approximation text. `"10"` / `"0"` / `"10.5"` ok; `"10 USDT"` / `"5元"` /
/// `"approx 10"` / `"10."` rejected.
fn is_valid_fee(fee: &str) -> bool {
    let fee = fee.trim();
    if fee.is_empty() {
        return false;
    }
    let mut parts = fee.split('.');
    let int_part = parts.next().unwrap_or("");
    let frac_part = parts.next();
    if parts.next().is_some() {
        return false; // more than one dot
    }
    if int_part.is_empty() || !int_part.bytes().all(|b| b.is_ascii_digit()) {
        return false;
    }
    if let Some(frac) = frac_part {
        if frac.is_empty() || frac.len() > 6 || !frac.bytes().all(|b| b.is_ascii_digit()) {
            return false;
        }
    }
    true
}

/// True for a syntactically acceptable public https endpoint (A2MCP only).
/// Rejects http/localhost/private-ranges/.local/.internal/placeholders and
/// anything longer than 512 chars.
fn is_valid_endpoint(url: &str) -> bool {
    let url = url.trim();
    if url.is_empty() || url.len() > 512 {
        return false;
    }
    let lower = url.to_lowercase();
    if !lower.starts_with("https://") {
        return false;
    }
    let host = lower
        .trim_start_matches("https://")
        .split(['/', ':', '?', '#'])
        .next()
        .unwrap_or("");
    if host.is_empty() {
        return false;
    }
    let bad_hosts = ["localhost", "127.0.0.1", "0.0.0.0", "example.com", "example.org"];
    if bad_hosts.contains(&host) {
        return false;
    }
    if host.ends_with(".local") || host.ends_with(".internal") {
        return false;
    }
    // RFC-1918 private ranges.
    if host.starts_with("10.") || host.starts_with("192.168.") {
        return false;
    }
    if host.starts_with("172.") {
        if let Some(second) = host.split('.').nth(1).and_then(|s| s.parse::<u8>().ok()) {
            if (16..=31).contains(&second) {
                return false;
            }
        }
    }
    true
}

/// Hard validation applied before a `create` / `update` network call. Emits the
/// exact bail strings the skill's `errors.md` maps to friendly rows.
fn validate_services(services: &[Value]) -> Result<()> {
    for svc in services {
        let name = svc.get("serviceName").and_then(Value::as_str).unwrap_or("");
        if name.trim().is_empty() {
            bail!("missing required field in --service: serviceName");
        }
        let desc = svc
            .get("serviceDescription")
            .and_then(Value::as_str)
            .unwrap_or("");
        if desc.trim().is_empty() {
            bail!("missing required field in --service: serviceDescription");
        }
        let stype_raw = svc.get("serviceType").and_then(Value::as_str).unwrap_or("");
        let stype = stype_raw.trim().to_uppercase();
        if stype != "A2MCP" && stype != "A2A" {
            bail!("invalid serviceType");
        }
        let fee = svc.get("fee").and_then(Value::as_str).unwrap_or("");
        if stype == "A2MCP" {
            if fee.trim().is_empty() {
                bail!("missing required field in --service: fee");
            }
            if !is_valid_fee(fee) {
                bail!("invalid fee in --service");
            }
            let endpoint = svc.get("endpoint").and_then(Value::as_str).unwrap_or("");
            if endpoint.trim().is_empty() {
                bail!("missing required field in --service: endpoint");
            }
            if !is_valid_endpoint(endpoint) {
                bail!("invalid endpoint in --service: must be a public https URL");
            }
        } else {
            // A2A: fee optional, but if present it must be a plain number.
            if !fee.trim().is_empty() && !is_valid_fee(fee) {
                bail!("invalid fee in --service");
            }
        }
    }
    Ok(())
}

// ── validate-listing (local QA, no network) ─────────────────────────────

fn is_cjk(c: char) -> bool {
    matches!(c as u32,
        0x4E00..=0x9FFF   // CJK Unified
        | 0x3400..=0x4DBF // CJK Ext A
        | 0x3040..=0x30FF // Hiragana + Katakana
        | 0xAC00..=0xD7AF // Hangul
        | 0xFF00..=0xFFEF // Fullwidth forms
    )
}

fn has_cjk(s: &str) -> bool {
    s.chars().any(is_cjk)
}

/// East-Asian display width (CJK = 2, others = 1) — matches the backend's
/// serviceDescription length accounting per invariants.md.
fn display_width(s: &str) -> usize {
    s.chars().map(|c| if is_cjk(c) { 2 } else { 1 }).sum()
}

fn finding(field: &str, code: &str, issue: &str, fix: &str) -> Value {
    json!({
        "field": field,
        "code": code,
        "severity": "block",
        "issue": issue,
        "fix": fix,
    })
}

/// Offline listing QA. Mirrors the mechanical rules the skill's register §4
/// describes; the returned `{ pass, findings[] }` shape is what the skill
/// renders. Semantic checks (celebrity names, 2-part structure) remain the
/// agent's job — the CLI reports only what it can verify deterministically.
fn validate_listing(
    role: &str,
    name: &str,
    description: &str,
    service: Option<&str>,
) -> Result<Value> {
    let role = parse_role(role)?;
    let services = parse_services(service)?;
    let mut findings: Vec<Value> = Vec::new();

    // Agent name length: CN 2–12 chars / EN 3–25 chars.
    let name_chars = name.chars().count();
    if has_cjk(name) {
        if !(2..=12).contains(&name_chars) {
            findings.push(finding(
                "name",
                "NAME_LEN",
                "Chinese agent name must be 2–12 characters.",
                "Shorten or lengthen the name to 2–12 characters.",
            ));
        }
    } else if !(3..=25).contains(&name_chars) {
        findings.push(finding(
            "name",
            "NAME_LEN",
            "English agent name must be 3–25 characters.",
            "Shorten or lengthen the name to 3–25 characters.",
        ));
    }

    // Agent description ≤500 chars (optional field).
    if description.chars().count() > 500 {
        findings.push(finding(
            "description",
            "DESC_LEN",
            "Agent description must be at most 500 characters.",
            "Trim the description to 500 characters or fewer.",
        ));
    }

    if role == "asp" {
        if services.is_empty() {
            findings.push(finding(
                "service",
                "SERVICE_REQUIRED",
                "An ASP needs at least one service.",
                "Add at least one service before submitting.",
            ));
        }
        for (i, svc) in services.iter().enumerate() {
            let sname = svc.get("serviceName").and_then(Value::as_str).unwrap_or("");
            let slen = sname.chars().count();
            if !(5..=30).contains(&slen) {
                findings.push(finding(
                    &format!("service[{i}].name"),
                    "SVC_NAME_LEN",
                    "Service name must be a 5–30 character noun phrase.",
                    "Rename the service to 5–30 characters.",
                ));
            }
            let sdesc = svc
                .get("serviceDescription")
                .and_then(Value::as_str)
                .unwrap_or("");
            if display_width(sdesc) > 400 {
                findings.push(finding(
                    &format!("service[{i}].description"),
                    "SVC_DESC_LEN",
                    "Service description exceeds the 400-width limit (CJK counts as 2).",
                    "Shorten the service description.",
                ));
            }
            let stype_raw = svc.get("serviceType").and_then(Value::as_str).unwrap_or("");
            let stype = stype_raw.trim().to_uppercase();
            if stype != "A2MCP" && stype != "A2A" {
                findings.push(finding(
                    &format!("service[{i}].serviceType"),
                    "SVC_TYPE",
                    "Service type must be API service (A2MCP) or agent to agent (A2A).",
                    "Set the type to API service or agent to agent.",
                ));
                continue;
            }
            let fee = svc.get("fee").and_then(Value::as_str).unwrap_or("");
            if stype == "A2MCP" {
                if fee.trim().is_empty() {
                    findings.push(finding(
                        &format!("service[{i}].fee"),
                        "SVC_FEE_REQUIRED",
                        "An API service requires a fee.",
                        "Set a plain-number fee (USDT is implied, e.g. 10).",
                    ));
                } else if !is_valid_fee(fee) {
                    findings.push(finding(
                        &format!("service[{i}].fee"),
                        "SVC_FEE",
                        "Fee must be a plain number with no currency and ≤6 decimals.",
                        "Use a bare number, e.g. 10 (not '10 USDT').",
                    ));
                }
                let endpoint = svc.get("endpoint").and_then(Value::as_str).unwrap_or("");
                if endpoint.trim().is_empty() {
                    findings.push(finding(
                        &format!("service[{i}].endpoint"),
                        "SVC_ENDPOINT_REQUIRED",
                        "An API service requires a public https endpoint.",
                        "Provide a deployed https:// URL.",
                    ));
                } else if !is_valid_endpoint(endpoint) {
                    findings.push(finding(
                        &format!("service[{i}].endpoint"),
                        "SVC_ENDPOINT",
                        "Endpoint must be a public https URL (no http/localhost/private IPs), ≤512 chars.",
                        "Use a publicly reachable https:// URL.",
                    ));
                }
            } else if !fee.trim().is_empty() && !is_valid_fee(fee) {
                findings.push(finding(
                    &format!("service[{i}].fee"),
                    "SVC_FEE",
                    "Fee must be a plain number with no currency and ≤6 decimals.",
                    "Use a bare number, e.g. 10, or leave empty for negotiable.",
                ));
            }
        }
    }

    Ok(json!({
        "pass": findings.is_empty(),
        "role": role,
        "findings": findings,
    }))
}

// ── Enrichment (best-effort, unambiguous fields only) ───────────────────

/// Add `roleLabel` to an agent object when a `role` / `agentRole` string is
/// present. Only maps the unambiguous role enum — status/approval label
/// mapping is left to the backend response (their integer scale is not
/// documented here) to avoid emitting a wrong label.
fn enrich_agent(agent: &mut Value) {
    let Some(obj) = agent.as_object_mut() else {
        return;
    };
    let role = obj
        .get("role")
        .or_else(|| obj.get("agentRole"))
        .and_then(Value::as_str)
        .map(str::to_string);
    if let Some(r) = role {
        let label = role_label(&r);
        if !label.is_empty() {
            obj.insert("roleLabel".to_string(), json!(label));
        }
    }
}

/// Walk a response of unknown shape (object with `list`, or a bare array) and
/// enrich each agent row's role label.
fn enrich_agent_list(data: &mut Value) {
    match data {
        Value::Array(rows) => rows.iter_mut().for_each(enrich_agent),
        Value::Object(obj) => {
            if let Some(Value::Array(rows)) = obj.get_mut("list") {
                rows.iter_mut().for_each(enrich_agent);
            }
        }
        _ => {}
    }
}

/// Add `serviceTypeLabel` + `feeDisplay` to each service row of a service-list
/// response.
fn enrich_services(data: &mut Value) {
    let rows: Option<&mut Vec<Value>> = match data {
        Value::Array(a) => Some(a),
        Value::Object(obj) => {
            let key = if obj.contains_key("services") {
                "services"
            } else {
                "list"
            };
            obj.get_mut(key).and_then(Value::as_array_mut)
        }
        _ => None,
    };
    let Some(rows) = rows else { return };
    for svc in rows.iter_mut() {
        let Some(obj) = svc.as_object_mut() else {
            continue;
        };
        let stype = obj
            .get("serviceType")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let label = service_type_label(&stype);
        if !label.is_empty() {
            obj.insert("serviceTypeLabel".to_string(), json!(label));
        }
        let fee = obj.get("fee").and_then(Value::as_str).unwrap_or("").to_string();
        obj.insert("feeDisplay".to_string(), json!(fee_display(&fee, &stype)));
    }
}

// ── Auth helper ─────────────────────────────────────────────────────────

/// Load the selected account id and build a fresh JWT-lifecycle client for an
/// authenticated write. Mirrors `competition::ensure_logged_in_client`.
async fn ensure_logged_in_client() -> Result<(String, ApiClient)> {
    let account_id = match wallet_store::load_wallets() {
        Ok(Some(w)) if !w.selected_account_id.is_empty() => w.selected_account_id.clone(),
        _ => bail!("not logged in — please run: onchainos wallet login"),
    };
    let client = ApiClient::new_async(None).await?;
    Ok((account_id, client))
}

/// POST an authed agent write, injecting `accountId` and the project header.
async fn authed_post(path: &str, mut body: Value) -> Result<Value> {
    let (account_id, mut client) = ensure_logged_in_client().await?;
    if let Some(obj) = body.as_object_mut() {
        obj.entry("accountId").or_insert(json!(account_id));
    }
    client
        .post_with_headers(path, &body, Some(&[("OK-ACCESS-PROJECT", PROJECT_HEADER)]))
        .await
}

// ── Network handlers ────────────────────────────────────────────────────

async fn pre_check(role: &str, consent_key: Option<&str>) -> Result<Value> {
    let role = parse_role(role)?;
    let mut body = json!({ "role": role });
    if let Some(key) = consent_key {
        body["consentKey"] = json!(key);
    }
    authed_post(EP_PRECHECK, body).await
}

async fn create(
    role: &str,
    name: &str,
    description: &str,
    picture: Option<&str>,
    service: Option<&str>,
) -> Result<Value> {
    let role = parse_role(role)?;
    if name.trim().is_empty() {
        bail!("missing required parameter: --name");
    }
    let services = parse_services(service)?;

    if role == "asp" {
        if picture.map(str::trim).unwrap_or("").is_empty() {
            bail!("ASP agents require an avatar");
        }
        if services.is_empty() {
            bail!("ASP agents require at least one service");
        }
    }
    validate_services(&services)?;

    let mut body = json!({
        "role": role,
        "name": name,
        "description": description,
        "service": services,
    });
    if let Some(pic) = picture {
        body["picture"] = json!(pic);
    }

    let mut data = authed_post(EP_CREATE, body).await?;
    // Normalize the id ladder: guarantee a `newAgentId` key (string or null)
    // so the skill's #id resolver has a stable slot to read.
    if let Some(obj) = data.as_object_mut() {
        if !obj.contains_key("newAgentId") {
            let derived = obj
                .get("agentId")
                .or_else(|| obj.get("id"))
                .cloned()
                .unwrap_or(Value::Null);
            obj.insert("newAgentId".to_string(), derived);
        }
    }
    Ok(data)
}

async fn update(
    agent_id: &str,
    name: Option<&str>,
    description: Option<&str>,
    picture: Option<&str>,
    service: Option<&str>,
) -> Result<Value> {
    if agent_id.trim().is_empty() {
        bail!("missing required parameter: --agent-id");
    }
    let services = parse_services(service)?;
    // Only validate service field shape; the update flow allows a subset and
    // per-element `operation` directives, so an empty array is valid here.
    validate_services(&services)?;

    let mut body = json!({ "agentId": agent_id });
    if let Some(v) = name {
        body["name"] = json!(v);
    }
    if let Some(v) = description {
        body["description"] = json!(v);
    }
    if let Some(v) = picture {
        body["picture"] = json!(v);
    }
    if service.is_some() {
        body["service"] = json!(services);
    }
    authed_post(EP_UPDATE, body).await
}

async fn get_my_agents() -> Result<Value> {
    let (account_id, mut client) = ensure_logged_in_client().await?;
    let mut data = client
        .get(EP_MY_AGENTS, &[("accountId", account_id.as_str())])
        .await?;
    enrich_agent_list(&mut data);
    Ok(data)
}

async fn get_agents(ctx: &Context, agent_ids: &str) -> Result<Value> {
    if agent_ids.trim().is_empty() {
        bail!("missing required parameter: --agent-ids");
    }
    let mut client = ctx.client_async().await?;
    let mut data = client.get(EP_DETAIL, &[("agentIds", agent_ids)]).await?;
    enrich_agent_list(&mut data);
    // detail responses are commonly a bare array — enrich those rows too.
    if data.is_array() {
        if let Some(rows) = data.as_array_mut() {
            rows.iter_mut().for_each(enrich_agent);
        }
    }
    Ok(data)
}

async fn activate(agent_id: &str, preferred_language: &str) -> Result<Value> {
    if agent_id.trim().is_empty() {
        bail!("missing required parameter: --agent-id");
    }
    if preferred_language.trim().is_empty() {
        bail!("missing required parameter: --preferred-language");
    }
    let body = json!({
        "agentId": agent_id,
        "preferredLanguage": preferred_language,
    });
    authed_post(EP_ACTIVATE, body).await
}

async fn deactivate(agent_id: &str) -> Result<Value> {
    if agent_id.trim().is_empty() {
        bail!("missing required parameter: --agent-id");
    }
    authed_post(EP_DEACTIVATE, json!({ "agentId": agent_id })).await
}

async fn upload(file: &str) -> Result<Value> {
    let bytes = std::fs::read(file).map_err(|_| anyhow::anyhow!("failed to read file"))?;
    if bytes.len() > MAX_AVATAR_BYTES {
        bail!("avatar file is larger than 1 MB — please send a smaller image");
    }
    let file_name = std::path::Path::new(file)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("avatar");
    let b64 = base64::engine::general_purpose::STANDARD.encode(&bytes);
    let body = json!({
        "fileName": file_name,
        "contentBase64": b64,
    });
    let data = authed_post(EP_UPLOAD, body).await?;
    // Surface the CDN url at the top level for --picture; the skill reads `url`.
    let url = data
        .get("url")
        .or_else(|| data.get("data").and_then(|d| d.get("url")))
        .cloned();
    match url {
        Some(u) if u.as_str().map(|s| !s.is_empty()).unwrap_or(false) => {
            Ok(json!({ "url": u }))
        }
        _ => bail!("upload response missing url"),
    }
}

#[allow(clippy::too_many_arguments)]
async fn search(
    ctx: &Context,
    query: &str,
    feedback: Option<&str>,
    agent_info: Option<&str>,
    status: Option<&str>,
    service: Option<&str>,
    page: u32,
) -> Result<Value> {
    if query.trim().is_empty() {
        bail!("missing required parameter: --query");
    }
    let page_s = page.to_string();
    let mut q: Vec<(&str, &str)> = vec![("query", query), ("page", &page_s)];
    if let Some(v) = feedback {
        q.push(("feedback", v));
    }
    if let Some(v) = agent_info {
        q.push(("agentInfo", v));
    }
    if let Some(v) = status {
        q.push(("status", v));
    }
    if let Some(v) = service {
        q.push(("service", v));
    }
    let mut client = ctx.client_async().await?;
    let mut data = client.get(EP_SEARCH, &q).await?;
    enrich_agent_list(&mut data);
    Ok(data)
}

async fn service_list(ctx: &Context, agent_id: &str) -> Result<Value> {
    if agent_id.trim().is_empty() {
        bail!("missing required parameter: --agent-id");
    }
    let mut client = ctx.client_async().await?;
    let mut data = client.get(EP_SERVICE_LIST, &[("agentId", agent_id)]).await?;
    enrich_services(&mut data);
    Ok(data)
}

async fn feedback_submit(agent_id: &str, rating: i64, description: &str) -> Result<Value> {
    if agent_id.trim().is_empty() {
        bail!("missing required parameter: --agent-id");
    }
    let body = json!({
        "agentId": agent_id,
        "rating": rating,
        "description": description,
    });
    authed_post(EP_FEEDBACK_SUBMIT, body).await
}

async fn feedback_list(ctx: &Context, agent_id: &str, page: u32) -> Result<Value> {
    if agent_id.trim().is_empty() {
        bail!("missing required parameter: --agent-id");
    }
    let page_s = page.to_string();
    let mut client = ctx.client_async().await?;
    client
        .get(EP_FEEDBACK_LIST, &[("agentId", agent_id), ("page", &page_s)])
        .await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn role_parsing_is_strict() {
        assert_eq!(parse_role("asp").unwrap(), "asp");
        assert_eq!(parse_role("USER").unwrap(), "user");
        assert_eq!(parse_role(" Evaluator ").unwrap(), "evaluator");
        assert!(parse_role("buyer").is_err());
        assert!(parse_role("2").is_err());
    }

    #[test]
    fn role_and_type_labels() {
        assert_eq!(role_label("asp"), "ASP");
        assert_eq!(role_label("user"), "User");
        assert_eq!(service_type_label("A2MCP"), "API service");
        assert_eq!(service_type_label("a2a"), "agent to agent");
        assert_eq!(service_type_label("weird"), "");
    }

    #[test]
    fn fee_display_rules() {
        assert_eq!(fee_display("10", "A2MCP"), "10 USDT");
        assert_eq!(fee_display("0", "A2MCP"), "0 USDT");
        assert_eq!(fee_display("", "A2MCP"), "free");
        assert_eq!(fee_display("", "A2A"), "negotiable");
    }

    #[test]
    fn fee_validation() {
        assert!(is_valid_fee("10"));
        assert!(is_valid_fee("0"));
        assert!(is_valid_fee("10.5"));
        assert!(is_valid_fee("0.123456"));
        assert!(!is_valid_fee("0.1234567")); // 7 dp
        assert!(!is_valid_fee("10 USDT"));
        assert!(!is_valid_fee("5元"));
        assert!(!is_valid_fee("approx 10"));
        assert!(!is_valid_fee("10."));
        assert!(!is_valid_fee(""));
        assert!(!is_valid_fee("1.2.3"));
    }

    #[test]
    fn endpoint_validation() {
        assert!(is_valid_endpoint("https://api.example.io/mcp"));
        assert!(!is_valid_endpoint("http://api.example.io"));
        assert!(!is_valid_endpoint("https://localhost/x"));
        assert!(!is_valid_endpoint("https://127.0.0.1:8080"));
        assert!(!is_valid_endpoint("https://10.0.0.5/x"));
        assert!(!is_valid_endpoint("https://192.168.1.1/x"));
        assert!(!is_valid_endpoint("https://172.16.0.1/x"));
        assert!(!is_valid_endpoint("https://svc.local/x"));
        assert!(!is_valid_endpoint("ftp://x"));
    }

    #[test]
    fn validate_services_bails_match_error_rows() {
        let svc = |v: Value| vec![v];
        // missing serviceName
        let e = validate_services(&svc(json!({"serviceType": "A2MCP"})))
            .unwrap_err()
            .to_string();
        assert_eq!(e, "missing required field in --service: serviceName");
        // invalid serviceType
        let e = validate_services(&svc(json!({
            "serviceName": "Token Price Feed",
            "serviceDescription": "d",
            "serviceType": "REST"
        })))
        .unwrap_err()
        .to_string();
        assert_eq!(e, "invalid serviceType");
        // A2MCP missing fee
        let e = validate_services(&svc(json!({
            "serviceName": "Token Price Feed",
            "serviceDescription": "d",
            "serviceType": "A2MCP"
        })))
        .unwrap_err()
        .to_string();
        assert_eq!(e, "missing required field in --service: fee");
        // A2MCP missing endpoint
        let e = validate_services(&svc(json!({
            "serviceName": "Token Price Feed",
            "serviceDescription": "d",
            "serviceType": "A2MCP",
            "fee": "10"
        })))
        .unwrap_err()
        .to_string();
        assert_eq!(e, "missing required field in --service: endpoint");
        // Valid A2MCP passes
        assert!(validate_services(&svc(json!({
            "serviceName": "Token Price Feed",
            "serviceDescription": "d",
            "serviceType": "A2MCP",
            "fee": "10",
            "endpoint": "https://api.example.io/mcp"
        })))
        .is_ok());
        // Valid A2A with no fee passes
        assert!(validate_services(&svc(json!({
            "serviceName": "Negotiated Research",
            "serviceDescription": "d",
            "serviceType": "A2A"
        })))
        .is_ok());
    }

    #[test]
    fn validate_listing_flags_short_service_name() {
        let out = validate_listing(
            "asp",
            "Acme Data",
            "",
            Some(r#"[{"serviceName":"Q","serviceDescription":"d","serviceType":"A2MCP","fee":"10","endpoint":"https://api.acme.io/mcp"}]"#),
        )
        .unwrap();
        assert_eq!(out["pass"], json!(false));
        let findings = out["findings"].as_array().unwrap();
        assert!(findings
            .iter()
            .any(|f| f["field"] == "service[0].name" && f["severity"] == "block"));
    }

    #[test]
    fn validate_listing_passes_clean_asp() {
        let out = validate_listing(
            "asp",
            "Acme Data",
            "On-chain data feeds",
            Some(r#"[{"serviceName":"Token Price Feed","serviceDescription":"Real-time token prices.\n1. token address 2. chain","serviceType":"A2MCP","fee":"10","endpoint":"https://api.acme.io/mcp"}]"#),
        )
        .unwrap();
        assert_eq!(out["pass"], json!(true), "findings: {}", out["findings"]);
    }

    #[test]
    fn validate_listing_flags_missing_service_for_asp() {
        let out = validate_listing("asp", "Acme Data", "", None).unwrap();
        assert_eq!(out["pass"], json!(false));
        let findings = out["findings"].as_array().unwrap();
        assert!(findings.iter().any(|f| f["field"] == "service"));
    }

    #[test]
    fn enrich_agent_adds_role_label() {
        let mut a = json!({"agentId": "42", "role": "asp", "name": "Acme"});
        enrich_agent(&mut a);
        assert_eq!(a["roleLabel"], json!("ASP"));
    }

    #[test]
    fn enrich_services_adds_type_label_and_fee() {
        let mut data = json!({"services": [
            {"serviceName": "x", "serviceType": "A2MCP", "fee": "10"},
            {"serviceName": "y", "serviceType": "A2A", "fee": ""}
        ]});
        enrich_services(&mut data);
        assert_eq!(data["services"][0]["serviceTypeLabel"], json!("API service"));
        assert_eq!(data["services"][0]["feeDisplay"], json!("10 USDT"));
        assert_eq!(data["services"][1]["serviceTypeLabel"], json!("agent to agent"));
        assert_eq!(data["services"][1]["feeDisplay"], json!("negotiable"));
    }

    #[test]
    fn parse_services_tolerates_single_object_and_empty() {
        assert_eq!(parse_services(None).unwrap().len(), 0);
        assert_eq!(parse_services(Some("")).unwrap().len(), 0);
        assert_eq!(
            parse_services(Some(r#"{"serviceName":"x"}"#)).unwrap().len(),
            1
        );
        assert_eq!(
            parse_services(Some(r#"[{"serviceName":"x"},{"serviceName":"y"}]"#))
                .unwrap()
                .len(),
            2
        );
    }
}
