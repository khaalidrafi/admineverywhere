/** TEMPORARY live-rig probe — NOT for commit. Runs against 127.0.0.1:8011. */
import { describe, expect, it } from "vitest";
import { fetchCsv, fetchSchema, login } from "../api";

const cfg: any = {
  apiUrl: "http://127.0.0.1:8011",
  authPath: "/api/auth/token/",
  schemaPath: "/api/schema/",
};

describe("live demo rig — FR-R005 discovery + fetch", () => {
  it("discovers exportPath from the LIVE schema and downloads the body once", async () => {
    const token = await login(cfg, "admin", "admin123");
    const schema = await fetchSchema(cfg, token);
    const orders = schema.byId.orders;
    console.log("discovered exportPath:", orders?.exportPath);
    expect(orders.exportPath).toBe("/api/orders/export/");
    for (const m of schema.models) {
      console.log("model", m.id, "exportPath:", m.exportPath ?? "(none)");
    }

    const file = await fetchCsv(cfg, token, orders.exportPath!, "fallback.csv");
    console.log("filename:", file.filename);
    console.log("bytes:", file.text.length, "BOM count at head:", /^﻿﻿/.test(file.text));
    expect(file.filename).toBe("orders-line.csv");
    expect(file.text.startsWith("﻿")).toBe(true);
    expect(file.text.startsWith("﻿﻿")).toBe(false);
    const lines = file.text.replace(/^﻿/, "").split("\r\n");
    console.log("header:", lines[0]);
    console.log("first row:", lines[1]);
    console.log("rows:", lines.filter((l) => l).length - 1);
    expect(lines[0]).toBe(
      "order_id,customer_id,customer,product_id,product,status,total,notes,created_at,history_id,from_status,to_status,history_actor,history_created_at",
    );
    expect(lines.filter((l) => l).length).toBeGreaterThan(60);
  }, 20000);
});
