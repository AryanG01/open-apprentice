"""Generates the demo library: ~100 colourful, realistic AI-infrastructure diagrams whose notes sit untidily next to
their boxes, so one taught layout rule has real work to do on all of them.

Owner-authored by construction (this script is the author; no external assets, no images, no fonts besides Helvetica).
Every file stays inside the release-1 import limits (classify.py): <= 32 objects, <= 16 single-line top-level text
labels, everything inside the page. Deterministic: the same seed writes byte-identical files.

    PYTHONPATH=src:. uv run python scripts/corpus/generate_library.py   # writes apps/web/public/samples/library
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

SEED = 20261019
OUT = Path("apps/web/public/samples/library")

# tier -> (fill, stroke, font colour); light fills so labels stay readable in any viewer
PALETTE = {
    "gpu": ("#e9f6d3", "#76b900", "#1f3b00"),
    "net": ("#ede7fb", "#7c4dff", "#2b1660"),
    "store": ("#e0f0fb", "#1e88e5", "#0b3558"),
    "serve": ("#fff1df", "#fb8c00", "#5a3000"),
    "data": ("#dff6f3", "#00897b", "#00332d"),
    "ctrl": ("#eceff1", "#546e7a", "#1c2a31"),
    "edge": ("#e8eaf6", "#3949ab", "#1a237e"),
    "guard": ("#fde7ec", "#d81b60", "#5c0d27"),
}

NOTES = {
    "gpu": [
        "8x H100 SXM",
        "8x B200",
        "FP8 training",
        "TP=8 PP=4",
        "NVLink 900 GB/s",
        "92% MFU",
        "8x GB200",
        "1.2M tok/s",
    ],
    "net": [
        "400 Gb/s NDR",
        "InfiniBand",
        "rail-optimised",
        "Spectrum-X",
        "RoCE v2",
        "2:1 oversub",
        "BlueField-3",
    ],
    "store": [
        "2.1 PB NVMe",
        "GPUDirect",
        "120 GB/s read",
        "S3 compatible",
        "3 replicas",
        "hot tier",
        "nightly backup",
    ],
    "serve": [
        "p99 38 ms",
        "NIM",
        "Triton",
        "batch 64",
        "autoscale 2-12",
        "99.95% SLO",
        "TensorRT-LLM",
    ],
    "data": [
        "parquet, 40 TB",
        "dedupe + filter",
        "NeMo Curator",
        "PII scrubbed",
        "streaming",
        "Iceberg tables",
    ],
    "ctrl": ["Base Command", "Slurm", "Kubernetes", "Prometheus", "GitOps", "RBAC", "audit log"],
    "edge": ["web + mobile", "12k RPS", "SSO login", "EU + US", "REST + gRPC"],
    "guard": ["NeMo Guardrails", "policy v3", "jailbreak filter", "PII redaction", "warning: beta"],
}

# theme: title, nodes [(slug, name, tier, col, row, optional)], edges [(a, b)]
THEMES = [
    (
        "AI factory pipeline",
        [
            ("ingest", "Ingest", "data", 0, 0, False),
            ("curate", "Curate", "data", 1, 0, False),
            ("tokenize", "Tokenize", "data", 2, 0, True),
            ("pretrain", "Pretrain", "gpu", 3, 0, False),
            ("finetune", "Fine-tune", "gpu", 3, 1, False),
            ("evaluate", "Evaluate", "ctrl", 2, 1, False),
            ("registry", "Model registry", "store", 1, 1, False),
            ("serve", "Serve", "serve", 0, 1, False),
            ("guard", "Guardrails", "guard", 0, 2, True),
            ("monitor", "Monitor", "ctrl", 1, 2, True),
        ],
        [
            ("ingest", "curate"),
            ("curate", "tokenize"),
            ("tokenize", "pretrain"),
            ("curate", "pretrain"),
            ("pretrain", "finetune"),
            ("finetune", "evaluate"),
            ("evaluate", "registry"),
            ("registry", "serve"),
            ("serve", "guard"),
            ("serve", "monitor"),
        ],
    ),
    (
        "DGX SuperPOD",
        [
            ("mgmt", "Mgmt fabric", "net", 0, 0, False),
            ("compute-fabric", "Compute fabric", "net", 1, 0, False),
            ("storage-fabric", "Storage fabric", "net", 2, 0, False),
            ("dgx-1", "DGX node 1", "gpu", 0, 1, False),
            ("dgx-2", "DGX node 2", "gpu", 1, 1, False),
            ("dgx-3", "DGX node 3", "gpu", 2, 1, False),
            ("dgx-4", "DGX node 4", "gpu", 3, 1, True),
            ("nvme", "NVMe tier", "store", 0, 2, False),
            ("object", "Object store", "store", 1, 2, True),
            ("scheduler", "Scheduler", "ctrl", 3, 0, False),
            ("telemetry", "Telemetry", "ctrl", 2, 2, True),
        ],
        [
            ("compute-fabric", "dgx-1"),
            ("compute-fabric", "dgx-2"),
            ("compute-fabric", "dgx-3"),
            ("compute-fabric", "dgx-4"),
            ("storage-fabric", "nvme"),
            ("storage-fabric", "object"),
            ("mgmt", "scheduler"),
            ("scheduler", "dgx-4"),
            ("dgx-3", "telemetry"),
        ],
    ),
    (
        "LLM inference serving",
        [
            ("clients", "Clients", "edge", 0, 0, False),
            ("gateway", "API gateway", "net", 1, 0, False),
            ("router", "Router", "serve", 2, 0, False),
            ("nim-1", "NIM replica 1", "serve", 1, 1, False),
            ("nim-2", "NIM replica 2", "serve", 2, 1, False),
            ("nim-3", "NIM replica 3", "serve", 3, 1, True),
            ("kv", "KV cache", "store", 3, 0, True),
            ("gpu-pool", "GPU pool", "gpu", 2, 2, False),
            ("guard", "Guardrails", "guard", 0, 1, False),
            ("metrics", "Metrics", "ctrl", 0, 2, True),
        ],
        [
            ("clients", "gateway"),
            ("gateway", "router"),
            ("router", "nim-1"),
            ("router", "nim-2"),
            ("router", "nim-3"),
            ("router", "kv"),
            ("nim-2", "gpu-pool"),
            ("gateway", "guard"),
            ("guard", "metrics"),
        ],
    ),
    (
        "RAG assistant",
        [
            ("user", "User", "edge", 0, 0, False),
            ("retriever", "Retriever", "data", 1, 0, False),
            ("vector-db", "Vector DB", "store", 2, 0, False),
            ("reranker", "Reranker", "serve", 2, 1, False),
            ("llm", "Nemotron", "gpu", 1, 1, False),
            ("guard", "Guardrails", "guard", 0, 1, False),
            ("docs", "Doc ingest", "data", 3, 0, True),
            ("embed", "Embedder", "gpu", 3, 1, True),
            ("eval", "Eval harness", "ctrl", 1, 2, True),
        ],
        [
            ("user", "retriever"),
            ("retriever", "vector-db"),
            ("vector-db", "reranker"),
            ("reranker", "llm"),
            ("llm", "guard"),
            ("docs", "embed"),
            ("embed", "vector-db"),
            ("llm", "eval"),
        ],
    ),
    (
        "Kubernetes GPU cluster",
        [
            ("ingress", "Ingress", "net", 0, 0, False),
            ("api", "API service", "serve", 1, 0, False),
            ("operator", "GPU operator", "ctrl", 2, 0, False),
            ("trainer", "Trainer pods", "gpu", 1, 1, False),
            ("inference", "Inference pods", "serve", 2, 1, False),
            ("node-a", "GPU node A", "gpu", 3, 1, False),
            ("node-b", "GPU node B", "gpu", 3, 2, True),
            ("pvc", "Volumes", "store", 0, 1, False),
            ("prom", "Prometheus", "ctrl", 0, 2, True),
            ("registry", "Image registry", "store", 1, 2, True),
        ],
        [
            ("ingress", "api"),
            ("api", "inference"),
            ("operator", "node-a"),
            ("operator", "node-b"),
            ("trainer", "node-a"),
            ("inference", "node-a"),
            ("trainer", "pvc"),
            ("prom", "trainer"),
        ],
    ),
    (
        "Data lakehouse for training",
        [
            ("logs", "Event logs", "data", 0, 0, False),
            ("crm", "CRM export", "data", 0, 1, False),
            ("web", "Web crawl", "data", 0, 2, True),
            ("stream", "Stream bus", "net", 1, 1, False),
            ("lake", "Lakehouse", "store", 2, 1, False),
            ("features", "Feature store", "store", 2, 0, False),
            ("curator", "Curator", "data", 2, 2, True),
            ("train", "Training jobs", "gpu", 3, 1, False),
            ("bi", "Dashboards", "ctrl", 3, 0, True),
        ],
        [
            ("logs", "stream"),
            ("crm", "stream"),
            ("web", "stream"),
            ("stream", "lake"),
            ("lake", "features"),
            ("lake", "curator"),
            ("features", "train"),
            ("curator", "train"),
            ("lake", "bi"),
        ],
    ),
]

NODE_W, NODE_H, COL, ROW, MARGIN, TOP = 150, 56, 210, 132, 40, 64
CHAR_W, LABEL_H = 7, 20


def _cell(cid: str, value: str, style: str, x: int, y: int, w: int, h: int) -> str:
    return (
        f'<mxCell id={quoteattr(cid)} parent="1" style={quoteattr(style)} value={quoteattr(value)} vertex="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" /></mxCell>'
    )


def diagram(i: int) -> tuple[str, str, int]:
    """(file name, xml, label count) of library diagram i."""
    rng = random.Random(SEED * 1000 + i)
    title, nodes, edges = THEMES[i % len(THEMES)]
    keep = [n for n in nodes if not n[5] or rng.random() < 0.6]
    slugs = {n[0] for n in keep}
    cols = max(n[3] for n in keep) + 1
    rows = max(n[4] for n in keep) + 1
    width, height = MARGIN * 2 + cols * COL - (COL - NODE_W), TOP + MARGIN + rows * ROW
    site = rng.choice(["us-west", "eu-north", "ap-south", "us-east", "eu-central", "ap-east"])
    cells = [
        _cell(
            "title",
            f"{title} · {site}-{i:03d}",
            "rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=none;fontSize=16;fontStyle=1;"
            "align=left;fontColor=#1c2a31;",
            MARGIN,
            16,
            min(width - 2 * MARGIN, 420),
            28,
        )
    ]
    pos = {}
    for slug, name, tier, col, row, _ in keep:
        fill, stroke, font = PALETTE[tier]
        x, y = MARGIN + col * COL, TOP + row * ROW
        pos[slug] = (x, y)
        cells.append(
            _cell(
                slug,
                name,
                f"rounded=1;arcSize=18;whiteSpace=wrap;html=1;fillColor={fill};"
                f"strokeColor={stroke};strokeWidth=2;fontColor={font};fontStyle=1;",
                x,
                y,
                NODE_W,
                NODE_H,
            )
        )
    grid = {n[0]: (n[3], n[4]) for n in keep}

    def tidy(
        a: str, b: str
    ) -> bool:  # only edges that route cleanly between neighbouring rows or columns
        (ca, ra), (cb, rb) = grid[a], grid[b]
        return abs(ra - rb) == 1 or (ra == rb and abs(ca - cb) == 1)

    links = [
        f'<mxCell id="edge-{k}" edge="1" parent="1" source="{a}" target="{b}" '
        'style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#b0bec5;strokeWidth=1.5;endArrow=block;'
        'endFill=1;"><mxGeometry relative="1" as="geometry" /></mxCell>'
        for k, (a, b) in enumerate(e for e in edges if e[0] in slugs and e[1] in slugs and tidy(*e))
    ]
    cells[1:1] = links  # edges first, so they are drawn beneath the boxes
    labels = 0
    for slug, name, tier, col, row, _ in keep:
        text = rng.choice(NOTES[tier])
        w = CHAR_W * len(text) + 12
        x, y = pos[slug]
        if (
            row == 0 or rng.random() < 0.65
        ):  # untidy: below (row 0 keeps clear of the title), off-centre, uneven gap
            lx, ly = x + rng.randint(-30, 30) + (NODE_W - w) // 2, y + NODE_H + rng.randint(2, 18)
        else:  # untidy: above the box
            lx, ly = x + rng.randint(-20, 20) + (NODE_W - w) // 2, y - LABEL_H - rng.randint(4, 12)
        lx = max(2, min(lx, width - w - 2))
        cells.append(
            _cell(
                f"{slug}-note",
                text,
                "text;html=1;align=left;verticalAlign=top;whiteSpace=nowrap;spacing=0;spacingTop=0;"
                "strokeColor=none;fillColor=none;fontSize=12;fontColor=#455a64;",
                lx,
                ly,
                w,
                LABEL_H,
            )
        )
        labels += 1
    xml = (
        '<mxfile host="open-apprentice-generator">'
        f'<diagram name="Page-1" id="lib-{i:03d}"><mxGraphModel grid="1" gridSize="10" page="1" pageScale="1" '
        f'pageWidth="{width}" pageHeight="{height}"><root><mxCell id="0" /><mxCell id="1" parent="0" />'
        + "".join(cells)
        + "</root></mxGraphModel></diagram></mxfile>\n"
    )
    slug = title.lower().replace(" ", "-")
    return f"{i:03d}-{slug}.drawio", xml, labels


def generate(out: Path = OUT, count: int = 100) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for i in range(count):
        name, xml, labels = diagram(i)
        data = xml.encode()
        (out / name).write_bytes(data)
        index.append(
            {
                "file": name,
                "title": THEMES[i % len(THEMES)][0],
                "labels": labels,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return index


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    files = generate(OUT, n)
    (OUT / "index.json").write_text(
        json.dumps(
            {"generator": "scripts/corpus/generate_library.py", "seed": SEED, "files": files},
            indent=1,
        )
        + "\n"
    )
    print(f"wrote {len(files)} diagrams to {OUT}")
