import { getDashboardSession } from "@/lib/dashboardAuth";
import { redirect } from "next/navigation";
import { OperatorCasinoManagement } from "@/components/OperatorCasinoManagement";

export default async function Page() {
  const session = await getDashboardSession("DASHBOARD_SECURITY_ADMIN");
  if (!session) redirect("/api/auth/login");
  
  return (
    <section className="card card-pad">
      <h2>Manajemen Casino & Options</h2>
      <OperatorCasinoManagement />
    </section>
  );
}