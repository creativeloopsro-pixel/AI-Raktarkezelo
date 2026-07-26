import { lazy, Suspense, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownToLine,
  Barcode,
  Boxes,
  ChevronRight,
  CloudUpload,
  ClipboardCheck,
  ClipboardList,
  FileSearch,
  FileSpreadsheet,
  FileText,
  Home,
  LayoutDashboard,
  LogOut,
  Mail,
  PackagePlus,
  Puzzle,
  Search,
  Settings,
  UserCog,
} from "lucide-react";

import { getProducts, getStock } from "../lib/api";
import type { Session } from "../types";
import { APP_VERSION } from "../version";
import DocumentsPage from "./DocumentsPage";
import EanBarcode from "./EanBarcode";
import EmailIntakePage from "./EmailIntakePage";
import PluginsPage from "./PluginsPage";
import ReceiptReviewPage from "./ReceiptReviewPage";
import ReviewTasksPage from "./ReviewTasksPage";
import VrpImportsPage from "./VrpImportsPage";

const InventoryPage = lazy(() => import("./InventoryPage"));
const UploadQueuePage = lazy(() => import("./UploadQueuePage"));
const IdentityPage = lazy(() => import("./IdentityPage"));
const SettingsPage = lazy(() => import("./SettingsPage"));
const ProductDialog = lazy(() => import("./ProductDialog"));
const StockDialog = lazy(() => import("./StockDialog"));

type Props = {
  session: Session;
  onSessionUpdated: (session: Session) => void;
  onLogout: () => void;
};

type WorkspaceView =
  | "overview"
  | "documents"
  | "reviews"
  | "receipt"
  | "inventory"
  | "uploads"
  | "identity"
  | "vrp"
  | "email"
  | "plugins"
  | "settings";

const formatter = new Intl.NumberFormat("hu-HU", { maximumFractionDigits: 3 });

export default function Dashboard({
  session,
  onSessionUpdated,
  onLogout
}: Props) {
  const [activeView, setActiveView] = useState<WorkspaceView>(() => {
    if (session.mfa_setup_required) return "identity";
    const requested = new URLSearchParams(window.location.search).get("view");
    return requested === "inventory" ||
      requested === "uploads" ||
      requested === "settings"
      ? requested
      : "overview";
  });
  const [search, setSearch] = useState("");
  const [productDialog, setProductDialog] = useState(false);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [selectedVrpBatchId, setSelectedVrpBatchId] = useState<string | null>(null);
  const [reviewOrigin, setReviewOrigin] = useState<"documents" | "vrp">(
    "documents"
  );
  const [stockMode, setStockMode] = useState<"receive" | "correct" | null>(null);

  const permissions = session.user.permissions ?? [];
  const can = (permission: string) => permissions.includes(permission);
  const locked = session.mfa_setup_required;
  const productsQuery = useQuery({
    queryKey: ["products"],
    queryFn: getProducts,
    enabled: !locked && can("products.read")
  });
  const stockQuery = useQuery({
    queryKey: ["stock"],
    queryFn: getStock,
    enabled: !locked && can("stock.read")
  });
  const products = useMemo(
    () => productsQuery.data ?? [],
    [productsQuery.data]
  );
  const stock = useMemo(() => stockQuery.data ?? [], [stockQuery.data]);

  const metrics = useMemo(() => {
    const totalQuantity = stock.reduce((sum, item) => sum + Number(item.quantity), 0);
    const lowStock = stock.filter(
      (item) => Number(item.quantity) <= Number(item.min_stock)
    );
    const negativeStock = stock.filter((item) => Number(item.quantity) < 0);
    return { totalQuantity, lowStock, negativeStock };
  }, [stock]);

  const primaryBarcodeByProductId = useMemo(
    () =>
      new Map(
        products.map((product) => [
          product.id,
          product.barcodes.find((barcode) => barcode.is_primary)?.code ??
            product.barcodes[0]?.code ??
            null
        ])
      ),
    [products]
  );

  const filteredStock = stock.filter((item) => {
    const needle = search.trim().toLocaleLowerCase("hu");
    const primaryBarcode = primaryBarcodeByProductId.get(item.product_id);
    return (
      !needle ||
      item.product_name.toLocaleLowerCase("hu").includes(needle) ||
      item.internal_sku.toLocaleLowerCase("hu").includes(needle) ||
      primaryBarcode?.includes(needle)
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
            <span>verzió {APP_VERSION}</span>
          </div>
        </div>
        <nav aria-label="Fő navigáció">
          {!locked && can("stock.read") && (
            <button
              className={`nav-item ${activeView === "overview" ? "active" : ""}`}
              onClick={() => setActiveView("overview")}
            >
              <LayoutDashboard aria-hidden="true" />
              Áttekintés
            </button>
          )}
          {!locked && can("inventory.count") && (
            <button
              className={`nav-item ${activeView === "inventory" ? "active" : ""}`}
              onClick={() => setActiveView("inventory")}
            >
              <ClipboardList aria-hidden="true" />
              Kézi leltár
            </button>
          )}
          {!locked && can("products.read") && (
            <button className="nav-item" onClick={() => setActiveView("overview")}>
              <Barcode aria-hidden="true" />
              Termékek
            </button>
          )}
          {!locked && can("documents.read") && (
            <button
              className={`nav-item ${
                ["documents", "receipt"].includes(activeView) ? "active" : ""
              }`}
              onClick={() => setActiveView("documents")}
            >
              <FileText aria-hidden="true" />
              Dokumentumok
            </button>
          )}
          {!locked && (can("documents.upload") || can("vrp.upload")) && (
            <button
              className={`nav-item ${activeView === "uploads" ? "active" : ""}`}
              onClick={() => setActiveView("uploads")}
            >
              <CloudUpload aria-hidden="true" />
              Feltöltési sor
            </button>
          )}
          {!locked && can("reviews.read") && (
            <button
              className={`nav-item ${activeView === "reviews" ? "active" : ""}`}
              onClick={() => {
                setReviewOrigin("documents");
                setActiveView("reviews");
              }}
            >
              <FileSearch aria-hidden="true" />
              Ellenőrzések
            </button>
          )}
          {!locked && can("vrp.read") && (
            <button
              className={`nav-item ${activeView === "vrp" ? "active" : ""}`}
              onClick={() => {
                setSelectedVrpBatchId(null);
                setActiveView("vrp");
              }}
            >
              <FileSpreadsheet aria-hidden="true" />
              VRP-import
            </button>
          )}
          {!locked && can("email.read") && (
            <button
              className={`nav-item ${activeView === "email" ? "active" : ""}`}
              onClick={() => setActiveView("email")}
            >
              <Mail aria-hidden="true" />
              E-mail postafiók
            </button>
          )}
          {!locked && can("plugins.read") && (
            <button
              className={`nav-item ${activeView === "plugins" ? "active" : ""}`}
              onClick={() => setActiveView("plugins")}
            >
              <Puzzle aria-hidden="true" />
              Pluginok
            </button>
          )}
          <button
            className={`nav-item ${activeView === "identity" ? "active" : ""}`}
            onClick={() => setActiveView("identity")}
          >
            <UserCog aria-hidden="true" />
            Felhasználók és biztonság
          </button>
        </nav>
        <div className="sidebar-footer">
          {!locked && (
            <button
              className={`nav-item ${activeView === "settings" ? "active" : ""}`}
              onClick={() => setActiveView("settings")}
              aria-current={activeView === "settings" ? "page" : undefined}
            >
              <Settings aria-hidden="true" />
              Beállítások
            </button>
          )}
          <button className="profile-button" onClick={onLogout}>
            <span className="avatar">
              {session.user.full_name.slice(0, 2).toUpperCase()}
            </span>
            <span>
              <strong>{session.user.full_name}</strong>
              <small>{session.user.roles?.join(", ") || session.user.role}</small>
            </span>
            <LogOut aria-label="Kijelentkezés" />
          </button>
        </div>
      </aside>

      <main className="workspace">
        {activeView === "settings" ? (
          <Suspense fallback={<div className="empty-state">Beállítások betöltése…</div>}>
            <SettingsPage
              session={session}
              onNavigate={(target) => setActiveView(target)}
            />
          </Suspense>
        ) : activeView === "identity" ? (
          <Suspense fallback={<div className="empty-state">Identity betöltése…</div>}>
            <IdentityPage
              session={session}
              onSessionUpdated={onSessionUpdated}
            />
          </Suspense>
        ) : activeView === "uploads" ? (
          <Suspense fallback={<div className="empty-state">Feltöltési sor betöltése…</div>}>
            <UploadQueuePage
              organizationId={session.user.organization_id}
              permissions={permissions}
              onOpenResult={(upload) => {
                if (upload.result_entity_type === "vrp_import_batch") {
                  setSelectedVrpBatchId(upload.result_entity_id);
                  setActiveView("vrp");
                } else {
                  setActiveView("documents");
                }
              }}
            />
          </Suspense>
        ) : activeView === "documents" ? (
          <DocumentsPage
            onUpload={() => setActiveView("uploads")}
            onOpenReviews={() => {
              setReviewOrigin("documents");
              setActiveView("reviews");
            }}
            onOpenReceipt={(documentId) => {
              setSelectedDocumentId(documentId);
              setActiveView("receipt");
            }}
          />
        ) : activeView === "reviews" ? (
          <ReviewTasksPage
            onBack={() => setActiveView(reviewOrigin)}
            onOpenReceipt={(documentId) => {
              setSelectedDocumentId(documentId);
              setActiveView("receipt");
            }}
            onOpenVrp={(batchId) => {
              setSelectedVrpBatchId(batchId);
              setActiveView("vrp");
            }}
          />
        ) : activeView === "receipt" && selectedDocumentId ? (
          <ReceiptReviewPage
            documentId={selectedDocumentId}
            products={products}
            onBack={() => setActiveView("documents")}
          />
        ) : activeView === "vrp" ? (
          <VrpImportsPage
            role={session.user.role}
            products={products}
            initialBatchId={selectedVrpBatchId}
            onOpenReviews={() => {
              setReviewOrigin("vrp");
              setActiveView("reviews");
            }}
          />
        ) : activeView === "email" ? (
          <EmailIntakePage role={session.user.role} />
        ) : activeView === "inventory" ? (
          <Suspense fallback={<div className="empty-state">Leltár betöltése…</div>}>
            <InventoryPage
              organizationId={session.user.organization_id}
              role={session.user.role}
            />
          </Suspense>
        ) : activeView === "plugins" ? (
          <PluginsPage role={session.user.role} />
        ) : (
          <>
            <header className="workspace-header">
              <div>
                <p className="eyebrow">Mai műszak</p>
                <h1>Készletáttekintés</h1>
              </div>
              <div className="header-actions">
                {can("stock.receive") && (
                  <button
                    className="secondary-button"
                    onClick={() => setStockMode("receive")}
                  >
                    <ArrowDownToLine aria-hidden="true" />
                    Bevételezés
                  </button>
                )}
                {can("products.write") && (
                  <button
                    className="primary-button"
                    onClick={() => setProductDialog(true)}
                  >
                    <PackagePlus aria-hidden="true" />
                    Új termék
                  </button>
                )}
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
                {can("stock.receive") && (
                  <motion.button
                    whileTap={{ scale: 0.98 }}
                    onClick={() => setStockMode("receive")}
                  >
                    <ArrowDownToLine aria-hidden="true" />
                    <span>
                      <strong>Áru érkezett</strong>
                      <small>Készlet növelése</small>
                    </span>
                    <ChevronRight aria-hidden="true" />
                  </motion.button>
                )}
                {can("inventory.count") && (
                  <motion.button
                    whileTap={{ scale: 0.98 }}
                    onClick={() => setActiveView("inventory")}
                  >
                    <ClipboardCheck aria-hidden="true" />
                    <span>
                      <strong>Készletet számoltam</strong>
                      <small>Eltérés rögzítése</small>
                    </span>
                    <ChevronRight aria-hidden="true" />
                  </motion.button>
                )}
                {(can("documents.upload") || can("vrp.upload")) && (
                  <motion.button
                    whileTap={{ scale: 0.98 }}
                    onClick={() => setActiveView("uploads")}
                  >
                    <CloudUpload aria-hidden="true" />
                    <span>
                      <strong>Fájlt töltök fel</strong>
                      <small>Offline is sorba állítható</small>
                    </span>
                    <ChevronRight aria-hidden="true" />
                  </motion.button>
                )}
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

              {loading && (
                <div className="empty-state">Készletadatok betöltése…</div>
              )}
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
                        const low =
                          Number(item.quantity) <= Number(item.min_stock);
                        const negative = Number(item.quantity) < 0;
                        return (
                          <motion.tr
                            key={item.product_id}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{
                              delay: Math.min(index * 0.025, 0.25)
                            }}
                          >
                            <td className="product-identity-cell">
                              <strong>{item.product_name}</strong>
                              <EanBarcode
                                code={
                                  primaryBarcodeByProductId.get(item.product_id) ??
                                  null
                                }
                                compact
                              />
                            </td>
                            <td className="muted-text">
                              {item.internal_sku}
                            </td>
                            <td>
                              <span
                                className={`status-dot ${
                                  negative ? "danger" : low ? "warning" : ""
                                }`}
                              >
                                {negative
                                  ? "Negatív"
                                  : low
                                    ? "Minimum alatt"
                                    : "Rendben"}
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
          </>
        )}
      </main>

      <nav className="mobile-actions many" aria-label="Mobil gyorsműveletek">
        {!locked && can("stock.read") && (
          <button
            className={activeView === "overview" ? "accent" : ""}
            onClick={() => setActiveView("overview")}
          >
            <Home aria-hidden="true" />
            Kezdő
          </button>
        )}
        {!locked && can("stock.receive") && (
          <button onClick={() => setStockMode("receive")}>
            <ArrowDownToLine aria-hidden="true" />
            Bevétel
          </button>
        )}
        {!locked && can("inventory.count") && (
          <button
            className={activeView === "inventory" ? "accent" : ""}
            onClick={() => setActiveView("inventory")}
          >
            <ClipboardList aria-hidden="true" />
            Leltár
          </button>
        )}
        {!locked && (can("documents.upload") || can("vrp.upload")) && (
          <button
            className={activeView === "uploads" ? "accent" : ""}
            onClick={() => setActiveView("uploads")}
          >
            <CloudUpload aria-hidden="true" />
            Feltöltés
          </button>
        )}
        {!locked && can("documents.read") && (
          <button
            className={
              ["documents", "receipt"].includes(activeView) ? "accent" : ""
            }
            onClick={() => setActiveView("documents")}
          >
            <FileText aria-hidden="true" />
            Iratok
          </button>
        )}
        {!locked && can("email.read") && (
          <button
            className={activeView === "email" ? "accent" : ""}
            onClick={() => setActiveView("email")}
          >
            <Mail aria-hidden="true" />
            E-mail
          </button>
        )}
        {!locked && can("vrp.read") && (
          <button
            className={activeView === "vrp" ? "accent" : ""}
            onClick={() => {
              setSelectedVrpBatchId(null);
              setActiveView("vrp");
            }}
          >
            <FileSpreadsheet aria-hidden="true" />
            VRP
          </button>
        )}
        {!locked && can("products.write") && (
          <button onClick={() => setProductDialog(true)}>
            <PackagePlus aria-hidden="true" />
            Termék
          </button>
        )}
        {!locked && can("plugins.read") && (
          <button
            className={activeView === "plugins" ? "accent" : ""}
            onClick={() => setActiveView("plugins")}
          >
            <Puzzle aria-hidden="true" />
            Plugin
          </button>
        )}
        <button
          className={activeView === "identity" ? "accent" : ""}
          onClick={() => setActiveView("identity")}
        >
          <UserCog aria-hidden="true" />
          Biztonság
        </button>
        {!locked && (
          <button
            className={activeView === "settings" ? "accent" : ""}
            onClick={() => setActiveView("settings")}
          >
            <Settings aria-hidden="true" />
            Beállítás
          </button>
        )}
      </nav>

      <Suspense fallback={null}>
        {productDialog ? (
          <ProductDialog open onOpenChange={setProductDialog} />
        ) : null}
        {stockMode ? (
          <StockDialog
            key={stockMode}
            mode={stockMode}
            products={products}
            open
            onOpenChange={(open) => !open && setStockMode(null)}
          />
        ) : null}
      </Suspense>
    </div>
  );
}
