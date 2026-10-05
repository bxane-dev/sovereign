#!/usr/bin/env bun
import React from "react";
import {render} from "ink";

import {App} from "./app.tsx";
import {SovereignApi} from "./client.ts";

const api = new SovereignApi(
  process.env.SOVEREIGN_API_URL ?? "http://127.0.0.1:8765",
);

render(<App api={api} />);
