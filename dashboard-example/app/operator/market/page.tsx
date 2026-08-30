import { getDashboardSession } from "@/lib/dashboardAuth";
import { redirect } from "next/navigation";
import { OperatorMarketManagement } from "@/components/OperatorMarketManagement";

export default async function Page() {
  const session = await getDashboardSession("DASHBOARD_SECURITY_ADMIN");
  if (!session) redirect("/api/auth/login");
  
  return (
    <section className="card card-pad">
      <h2>Manajemen Marketplace</h2>
      <OperatorMarketManagement />
    </section>
  );
}