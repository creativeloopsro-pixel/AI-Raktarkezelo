import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownToLine,
  Barcode,
  Boxes,
  ChevronRight,
  ClipboardCheck,
  FileText,
  LayoutDashboard,
  LogOut,
  PackagePlus,
  Search,
  Settings,
  Sparkles,
  Warehouse
} from "lucide-react";

import { getProducts, getStock } from "../lib/api";
import type { Session } from "../types";
import ProductDialog from "./ProductDialog";
import StockDialog from "./StockDialog";

type Props = {
  session: Session;
  onLogout: () => void;
};

const formatter = new Intl.NumberFormat("hu-HU", { maximumFractionDigits: 3 });

export default function Dashboard({ session, onLogout }: Props) {
  const [search, setSearch] = useState("");
  const [productDialog, setProductDialog] = useState(false);
  const [stockMode, setStockMode] = useState<"receive" | "correct" | null>(null);

  const productsQuery = useQuery({ queryKey: ["products"], queryFn: getProducts });
  const stockQuery = useQuery({ queryKey: ["stock"], queryFn: getStock });
  const products = productsQuery.data ?? [];
  const stock = useMemo(() => stockQuery.data ?? [], [stockQuery.data]);

  const metrics = useMemo(() => {
    const totalQuantity = stock.reduce((sum, item) => sum + Number(item.quantity), 0);
    const lowStock = stock.filter((item) => Number(item.quantity) <= Number(item.min_stock));
    const negativeStock = stock.filter((item) => Number(item.quantity) < 0);
    return { totalQuantity, lowStock, negativeStock };
  }, [stock]);

  const filteredStock = stock.filter((item) => {
    const needle = search.trim().toLocaleLowerCase("hu");
    return (
      !needle ||
      item.product_name.toLocaleLowerCase("hu").includes(needle) ||
      item.internal_sku.toLocaleLowerCase("hu").includes(needle)
    );
  });

  const loading = productsQuery.isLoading || stockQuery.isLoading;
  const failed = productsQuery.isError || stockQuery.isError;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark small">
            <Boxes aria-hidden="true" />
          </div>
          <div>
            <strong>AI Raktár</strong>
            <span>verzió 0.1.0</span>
          </div>
        </div>
        <nav aria-label="Fő navigáció">
          <button className="nav-item active">
            <LayoutDashboard aria-hidden="true" />
            Áttekintés
          </button>
          <button className="nav-item">
            <Warehouse aria-hidden="true" />
            Készlet
          </button>
          <button className="nav-item">
            <Barcode aria-hidden="true" />
            Termékek
          </button>
          <button className="nav-item muted" title="A következő kiadásban">
            <FileText aria-hidden="true" />
            Dokumentumok
          </button>
          <button className="nav-item muted" title="A következő kiadásban">
            <Sparkles aria-hidden="true" />
            AI ellenőrzés
          </button>
        </nav>
        <div className="sidebar-footer">
          <button className="nav-item">
            <Settings aria-hidden="true" />
            Beállítások
          </button>
          <button className="profile-button" onClick={onLogout}>
            <span className="avatar">{session.user.full_name.slice(0, 2).toUpperCase()}</span>
            <span>
              <strong>{session.user.full_name}</strong>
              <small>{session.user.role}</small>
            </span>
            <LogOut aria-label="Kijelentkezés" />
          </button>
        </div>
      </aside>

      <main className="workspace">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">Mai műszak</p>
            <h1>Készletáttekintés</h1>
          </div>
          <div className="header-actions">
            <button className="secondary-button" onClick={() => setStockMode("receive")}>
              <ArrowDownToLine aria-hidden="true" />
              Bevételezés
            </button>
            <button className="primary-button" onClick={() => setProductDialog(true)}>
              <PackagePlus aria-hidden="true" />
              Új termék
            </button>
          </div>
        </header>

        <motion.section
          className="metric-strip"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          aria-label="Készletmutatók"
        >
          <div>
            <span>Aktív termék</span>
            <strong>{formatter.format(products.length)}</strong>
            <small>terméktörzsben</small>
          </div>
          <div>
            <span>Összes készlet</span>
            <strong>{formatter.format(metrics.totalQuantity)}</strong>
            <small>alapegység</small>
          </div>
          <div className={metrics.lowStock.length ? "attention" : ""}>
            <span>Minimum alatt</span>
            <strong>{formatter.format(metrics.lowStock.length)}</strong>
            <small>figyelmet kér</small>
          </div>
          <div className={metrics.negativeStock.length ? "danger" : ""}>
            <span>Negatív készlet</span>
            <strong>{formatter.format(metrics.negativeStock.length)}</strong>
            <small>ellenőrizendő</small>
          </div>
        </motion.section>

        <section className="action-band">
          <div>
            <p className="section-label">Gyors műveletek</p>
            <h2>Mit szeretnél rögzíteni?</h2>
          </div>
          <div className="quick-actions">
            <motion.button whileTap={{ scale: 0.98 }} onClick={() => setStockMode("receive")}>
              <ArrowDownToLine aria-hidden="true" />
              <span>
                <strong>Áru érkezett</strong>
                <small>Készlet növelése</small>
              </span>
              <ChevronRight aria-hidden="true" />
            </motion.button>
            <motion.button whileTap={{ scale: 0.98 }} onClick={() => setStockMode("correct")}>
              <ClipboardCheck aria-hidden="true" />
              <span>
                <strong>Készletet számoltam</strong>
                <small>Eltérés rögzítése</small>
              </span>
              <ChevronRight aria-hidden="true" />
            </motion.button>
          </div>
        </section>

        <motion.section
          className="stock-section"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.15, duration: 0.35 }}
        >
          <div className="section-heading">
            <div>
              <p className="section-label">Aktuális állapot</p>
              <h2>Termékek és készlet</h2>
            </div>
            <label className="search-field">
              <Search aria-hidden="true" />
              <span className="sr-only">Keresés</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Termék vagy SKU keresése"
              />
            </label>
          </div>

          {loading && <div className="empty-state">Készletadatok betöltése…</div>}
          {failed && (
            <div className="empty-state error-state">
              <AlertTriangle aria-hidden="true" />
              Az adatok most nem érhetők el. Ellenőrizd az API-kapcsolatot.
            </div>
          )}
          {!loading && !failed && filteredStock.length === 0 && (
            <div className="empty-state">
              <Boxes aria-hidden="true" />
              <strong>Még nincs megjeleníthető termék.</strong>
              <span>Hozd létre az első terméket a jobb felső gombbal.</span>
            </div>
          )}
          {!loading && !failed && filteredStock.length > 0 && (
            <div className="stock-table-wrap">
              <table className="stock-table">
                <thead>
                  <tr>
                    <th>Termék</th>
                    <th>SKU</th>
                    <th>Állapot</th>
                    <th className="numeric">Készlet</th>
                    <th className="numeric">Minimum</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredStock.map((item, index) => {
                    const low = Number(item.quantity) <= Number(item.min_stock);
                    const negative = Number(item.quantity) < 0;
                    return (
                      <motion.tr
                        key={item.product_id}
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: Math.min(index * 0.025, 0.25) }}
                      >
                        <td>
                          <strong>{item.product_name}</strong>
                        </td>
                        <td className="muted-text">{item.internal_sku}</td>
                        <td>
                          <span className={`status-dot ${negative ? "danger" : low ? "warning" : ""}`}>
                            {negative ? "Negatív" : low ? "Minimum alatt" : "Rendben"}
                          </span>
                        </td>
                        <td className="numeric quantity-cell">
                          {formatter.format(Number(item.quantity))}
                        </td>
                        <td className="numeric muted-text">
                          {formatter.format(Number(item.min_stock))}
                        </td>
                      </motion.tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </motion.section>
      </main>

      <nav className="mobile-actions" aria-label="Mobil gyorsműveletek">
        <button onClick={() => setStockMode("receive")}>
          <ArrowDownToLine aria-hidden="true" />
          Bevételezés
        </button>
        <button className="accent" onClick={() => setStockMode("correct")}>
          <ClipboardCheck aria-hidden="true" />
          Számlálás
        </button>
        <button onClick={() => setProductDialog(true)}>
          <PackagePlus aria-hidden="true" />
          Új termék
        </button>
      </nav>

      <ProductDialog open={productDialog} onOpenChange={setProductDialog} />
      <StockDialog
        key={stockMode ?? "closed"}
        mode={stockMode ?? "receive"}
        products={products}
        open={stockMode !== null}
        onOpenChange={(open) => !open && setStockMode(null)}
      />
    </div>
  );
}
