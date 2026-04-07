import { NextRequest } from "next/server";
import { supabase } from "@/lib/supabase";

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code") ?? "";

  if (!code) {
    return Response.json({ error: "code param required" });
  }

  // Direct query to urun_barkod
  const { data, error } = await supabase
    .from("urun_barkod")
    .select("*")
    .eq("barkod", code)
    .limit(5);

  // Also try numeric
  const { data: data2, error: error2 } = await supabase
    .from("urun_barkod")
    .select("*")
    .eq("barkod", Number(code))
    .limit(5);

  // Check table exists by fetching 1 row
  const { data: sample, error: sampleErr } = await supabase
    .from("urun_barkod")
    .select("*")
    .limit(1);

  return Response.json({
    barcode: code,
    string_match: { data, error },
    numeric_match: { data: data2, error: error2 },
    sample_row: { data: sample, error: sampleErr },
  });
}
