import { redirect } from "next/navigation";
import { requireDashboardSession } from "@/lib/dashboardAuth";

export default async function RootPage() {
  await requireDashboardSession();
  redirect("/economy");
}
