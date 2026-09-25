#!/usr/bin/env python3
"""
Directly ingest O2OA runtime service descriptors into data.db,
following the same format as existing o2oa_api documents.
Then reindex to add them to the vector KB.
"""

import os, json, re, time, sqlite3, httpx

BASE = r"D:/O2OA/o2server/servers/webServer/o2_core/o2/xAction/services"
CATEGORY = "o2oa_api"
TOKEN = "local-o2-agent-2026"

# Map each service module filename to a readable action name for the doc ID.
MODULE_TO_ACTION = {
    "x_attendance_assemble_control":  "AttendanceAction",
    "x_bbs_assemble_control":         "BBSAction",
    "x_calendar_assemble_control":    "CalendarAction",
    "x_cms_assemble_control":         "CMSBlockAction",
    "x_collaboration_assemble_websocket": "WebSocketAction",
    "x_component_assemble_control":   "ComponentAction",
    "x_faceset_control":              "FaceSetAction",
    "x_file_assemble_control":        "FileAction",
    "x_general_assemble_control":     "GeneralAction",
    "x_hotpic_assemble_control":      "HotPicAction",
    "x_meeting_assemble_control":     "MeetingAction",
    "x_message_assemble_communicate": "MessageCommunicateAction",
    "x_mind_assemble_control":        "MindAction",
    "x_okr_assemble_control":         "OKRAction",
    "x_organization_assemble_authentication": "AuthAction",
    "x_organization_assemble_control":  "OrganizationAction",
    "x_organization_assemble_express":  "OrganizationExpressAction",
    "x_organization_assemble_personal": "PersonalAction",
    "x_portal_assemble_designer":     "PortalDesignerAction",
    "x_portal_assemble_surface":      "PortalSurfaceAction",
    "x_processplatform_assemble_bam":   "BAMAction",
    "x_processplatform_assemble_designer": "DesignerAction",
    "x_processplatform_assemble_surface": "ProcessPlatformSurfaceAction",
    "x_program_center":               "ProgramCenterAction",
    "x_query_assemble_designer":      "QueryDesignerAction",
    "x_query_assemble_surface":       "QuerySurfaceAction",
    "x_smartoffice_control":          "SmartOfficeControl",
    "x_strategydeploy_assemble_control":"StrategyDeployAction",
    "x_teamwork_assemble_control":    "TeamworkAction",
}


def strip_comments(text: str) -> str:
    """Remove /* */ block comments and // line comments from JSON-like text."""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    lines = text.splitlines()
    out_lines = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("//"):
            continue
        idx = stripped.find("//")
        while idx != -1:
            before = stripped[:idx]
            qcount = before.count('"')
            if qcount % 2 == 0:
                stripped = stripped[:idx]
                break
            else:
                idx = stripped.find("//", idx + 2)
        out_lines.append(stripped)
    return "\n".join(out_lines)


def extract_operations(data):
    """Extract operation list from the parsed JSON dict."""
    lines = []
    for op_name, op_info in data.items():
        if not isinstance(op_info, dict):
            continue
        uri = op_info.get("uri", "")
        method = op_info.get("method", "GET")
        lines.append(f"  - {op_name}: {method} {uri}")
    return "\n".join(lines)


def generate_doc_content(module_name, ops_text):
    """Generate markdown content in the format of existing o2oa_api docs."""
    module_display = module_name.replace("x_", "").replace("_", " ").title()
    content = f"""# O2OA API 模块: {module_display}

## 接口列表

{ops_text}

*以上接口已通过 O2OA 运行态 :9090 /o2_core/o2/xAction/services/*.json 入库，支持 RAG 检索。*
"""
    return content


def reindex_doc(doc_id):
    """Call the gateway's reindex function to vectorize the new doc."""
    url = "http://127.0.0.1:18790/gateway/reindex_doc"
    headers = {"Authorization": TOKEN, "Content-Type": "application/json"}
    payload = {"doc_id": doc_id}
    resp = httpx.post(url, headers=headers, json=payload, timeout=30)
    return resp


def main():
    json_files = sorted([
        os.path.join(BASE, f) 
        for f in os.listdir(BASE) 
        if f.endswith(".json")
    ])
    print(f"Found {len(json_files)} service JSON files in {BASE}")
    
    success = 0
    skipped = 0
    
    db = sqlite3.connect('D:/O2OA/gateway/data.db')
    
    for i, fpath in enumerate(json_files, 1):
        raw = open(fpath, "r", encoding="utf-8").read()
        cleaned = strip_comments(raw)
        
        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  [SKIP] {os.path.basename(fpath)}: parse error - {e}")
            skipped += 1
            continue
        
        fname = os.path.splitext(os.path.basename(fpath))[0]
        action_name = MODULE_TO_ACTION.get(fname)
        if not action_name:
            print(f"  [SKIP] {fname}: no action name mapping")
            skipped += 1
            continue
        
        doc_id = f"o2kb::o2oa_api::{action_name}"
        ops_text = extract_operations(data)
        content = generate_doc_content(fname, ops_text)
        
        # Check if already exists (idempotent)
        existing = db.execute(
            "SELECT id FROM docs WHERE category=? AND id=?", 
            (CATEGORY, doc_id)).fetchone()
        if existing:
            print(f"  [SKIP] {doc_id}: already exists, skipping")
            skipped += 1
            continue
        
        # Insert into docs table
        db.execute("""
            INSERT INTO docs(id, title, category, content, creator_person, creator_unit,
                           question_enable, permission, meta, updated)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, f"O2OA API - {action_name}", CATEGORY, content,
             "AI助手", "", 1, json.dumps([], ensure_ascii=False),
             json.dumps({"topic": "o2oa_api_services"}, ensure_ascii=False),
             time.time()))
        
        # Reindex to add to vector KB
        try:
            resp = reindex_doc(doc_id)
            print(f"  [OK] {doc_id} reindex: HTTP {resp.status_code}")
        except Exception as e:
            print(f"  [WARN] reindex failed for {doc_id}: {e}")
        
        db.commit()
        success += 1
    
    db.close()
    
    print(f"\nDone: {success} succeeded, {skipped} skipped out of {len(json_files)} files.")
    

if __name__ == "__main__":
    main()
