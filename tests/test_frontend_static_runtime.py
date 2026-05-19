from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path


def run_app_config(search: str, hostname: str, stored_api_base: str = "") -> dict[str, object]:
    script = textwrap.dedent(
        f"""
        const fs = require("fs");
        const vm = require("vm");
        const listeners = {{}};
        const element = () => ({{
          dataset: {{}},
          style: {{}},
          addEventListener: (name, cb) => {{ listeners[name] = cb; }},
          textContent: "",
          innerHTML: "",
          value: "30",
          replaceChildren: () => {{}},
        }});
        const map = {{
          setView: () => map,
          on: () => {{}},
          invalidateSize: () => {{}},
          fitBounds: () => {{}},
        }};
        const context = {{
          console,
          URLSearchParams,
          Number,
          Math,
          setTimeout: () => 0,
          clearTimeout: () => {{}},
          requestAnimationFrame: (cb) => cb(),
          fetch: () => Promise.resolve({{
            ok: true,
            json: () => Promise.resolve({{
              v: 1,
              constants: {{}},
              default_center: [47.376, 8.541],
              stops: [["A", "Zurich Alpha", 47.376, 8.541, "zurich alpha"]],
              grid: {{"4737:854": [0]}},
              ride_edges: [[]],
              walk_edges: [[]],
            }}),
          }}),
          window: {{
            location: {{ search: {json.dumps(search)}, hostname: {json.dumps(hostname)}, protocol: "https:" }},
            localStorage: {{ getItem: () => {json.dumps(stored_api_base)} }},
          }},
          document: {{
            getElementById: () => element(),
            createElement: () => element(),
          }},
          L: {{
            map: () => map,
            tileLayer: () => ({{ addTo: () => {{}} }}),
            marker: () => ({{ addTo: () => ({{ bindPopup: () => {{}} }}) }}),
            Layer: {{ extend: () => function() {{}} }},
            latLngBounds: () => ({{ extend: () => {{}} }}),
            DomUtil: {{
              create: () => ({{ style: {{}}, getContext: () => null }}),
              setPosition: () => {{}},
              remove: () => {{}},
            }},
          }},
        }};
        context.window.window = context.window;
        context.window.__transitHeatMapInternals = null;
        vm.createContext(context);
        vm.runInContext(fs.readFileSync("frontend/app.js", "utf8"), context);
        process.stdout.write(JSON.stringify(context.window.__transitHeatMapInternals));
        """
    )
    result = subprocess.run(
        ["node", "-e", script],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_static_query_ignores_stored_api_base():
    config = run_app_config("?static=1", "drichter-official.github.io", "http://localhost:8000")

    assert config["USE_STATIC_DATA"] is True
    assert config["API_BASE"] == ""


def test_custom_domain_defaults_to_static_when_no_api_is_explicit():
    config = run_app_config("", "transit.example.com", "http://localhost:8000")

    assert config["USE_STATIC_DATA"] is True
    assert config["API_BASE"] == ""


def test_explicit_api_disables_static_mode():
    config = run_app_config("?api=https://api.example.com", "drichter-official.github.io", "")

    assert config["USE_STATIC_DATA"] is False
    assert config["API_BASE"] == "https://api.example.com"
