import { getDashboardSession } from "@/lib/dashboardAuth";
import { redirect } from "next/navigation";
import { OperatorCryptoManagement } from "@/components/OperatorCryptoManagement";

export default async function Page() {
  const session = await getDashboardSession("DASHBOARD_SECURITY_ADMIN");
  if (!session) redirect("/api/auth/login");
  
  return (
    <section className="card card-pad">
      <h2>Manajemen Crypto & Mining</h2>
      <OperatorCryptoManagement />
    </section>
  );
}