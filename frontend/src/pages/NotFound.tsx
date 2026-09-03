import { Link } from "react-router-dom";
import { useLanguage } from "../lib/i18n";

export default function NotFound() {
  const { t } = useLanguage();
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 py-24 text-center">
      <p className="text-3xl font-black text-[var(--color-ink-faint)]">404</p>
      <p className="text-sm text-[var(--color-ink-muted)]">{t("notFound.message")}</p>
      <Link to="/" className="btn btn-primary mt-2">
        {t("notFound.backToOverview")}
      </Link>
    </div>
  );
}
