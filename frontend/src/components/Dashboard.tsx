import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState
} from "react";
import * as Dialog from "@radix-ui/react-dialog";
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
  MoreHorizontal,
  PackagePlus,
  Puzzle,
  Search,
  Settings,
  UserCog,
  X
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
const ProductReceivingDialog = lazy(
  () => import("./ProductReceivingDialog")
);
const ProductsPage = lazy(() => import("./ProductsPage"));
const StockDialog = lazy(() => import("./StockDialog"));

type Props = {
  session: Session;
  onSessionUpdated: (session: Session) => void;
  onLogout: () => void;
};

type WorkspaceView =
  | "overview"
  | "products"
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

type ReceiveMode = "delivery_note" | "barcode";
type IdentityTab = "users" | "roles" | "security" | "tokens";

type RouteState = {
  view: WorkspaceView;
  documentId: string | null;
  vrpBatchId: string | null;
  identityTab: IdentityTab;
  settingsAi: boolean;
  settingsReports: boolean;
};

const formatter = new Intl.NumberFormat("hu-HU", { maximumFractionDigits: 3 });

function readRoute(locked: boolean): RouteState {
  if (locked) {
    return {
      view: "identity",
      documentId: null,
      vrpBatchId: null,
      identityTab: "security",
      settingsAi: false,
      settingsReports: false
    };
  }

  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  const legacyView = new URLSearchParams(window.location.search).get("view");
  const defaults: RouteState = {
    view: "overview",
    documentId: null,
    vrpBatchId: null,
    identityTab: "users",
    settingsAi: false,
    settingsReports: false
  };

  if (path === "/" && legacyView) {
    const legacyMap: Partial<Record<string, WorkspaceView>> = {
      products: "products",
      inventory: "inventory",
      uploads: "uploads",
      settings: "settings"
    };
    return { ...defaults, view: legacyMap[legacyView] ?? "overview" };
  }
  if (path === "/dashboard" || path === "/") return defaults;
  if (path === "/products") return { ...defaults, view: "products" };
  if (path === "/inventory") return { ...defaults, view: "inventory" };
  if (path === "/documents") return { ...defaults, view: "documents" };
  if (path === "/documents/uploads") return { ...defaults, view: "uploads" };
  if (path === "/documents/reviews") return { ...defaults, view: "reviews" };
  if (path.startsWith("/documents/receipts/")) {
    return {
      ...defaults,
      view: "receipt",
      documentId: decodeURIComponent(path.slice("/documents/receipts/".length))
    };
  }
  if (path === "/vrp") return { ...defaults, view: "vrp" };
  if (path.startsWith("/vrp/")) {
    return {
      ...defaults,
      view: "vrp",
      vrpBatchId: decodeURIComponent(path.slice("/vrp/".length))
    };
  }
  if (path === "/email") return { ...defaults, view: "email" };
  if (path === "/plugins") return { ...defaults, view: "plugins" };
  if (
    path === "/settings" ||
    path === "/settings/ai" ||
    path === "/settings/reports"
  ) {
    return {
      ...defaults,
      view: "settings",
      settingsAi: path === "/settings/ai",
      settingsReports: path === "/settings/reports"
    };
  }
  const identityRoutes: Record<string, IdentityTab> = {
    "/admin/users": "users",
    "/admin/roles": "roles",
    "/admin/security": "security",
    "/admin/api-tokens": "tokens"
  };
  if (identityRoutes[path]) {
    return {
      ...defaults,
      view: "identity",
      identityTab: identityRoutes[path]
    };
  }
  return defaults;
}

function routePath(route: RouteState): string {
  if (route.view === "products") return "/products";
  if (route.view === "inventory") return "/inventory";
  if (route.view === "documents") return "/documents";
  if (route.view === "uploads") return "/documents/uploads";
  if (route.view === "reviews") return "/documents/reviews";
  if (route.view === "receipt" && route.documentId) {
    return `/documents/receipts/${encodeURIComponent(route.documentId)}`;
  }
  if (route.view === "vrp") {
    return route.vrpBatchId
      ? `/vrp/${encodeURIComponent(route.vrpBatchId)}`
      : "/vrp";
  }
  if (route.view === "email") return "/email";
  if (route.view === "plugins") return "/plugins";
  if (route.view === "settings") {
    if (route.settingsAi) return "/settings/ai";
    if (route.settingsReports) return "/settings/reports";
    return "/settings";
  }
  if (route.view === "identity") {
    const identityPaths: Record<IdentityTab, string> = {
      users: "/admin/users",
      roles: "/admin/roles",
      security: "/admin/security",
      tokens: "/admin/api-tokens"
    };
    return identityPaths[route.identityTab];
  }
  return "/dashboard";
}

export default function Dashboard({
  session,
  onSessionUpdated,
  onLogout
}: Props) {
  const locked = session.mfa_setup_required;
  const [initialRoute] = useState(() => readRoute(locked));
  const [activeView, setActiveView] = useState<WorkspaceView>(initialRoute.view);
  const [identityTab, setIdentityTab] = useState<IdentityTab>(
    initialRoute.identityTab
  );
  const [settingsAi, setSettingsAi] = useState(initialRoute.settingsAi);
  const [settingsReports, setSettingsReports] = useState(
    initialRoute.settingsReports
  );
  const [search, setSearch] = useState("");
  const [productDialog, setProductDialog] = useState(false);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(
    initialRoute.documentId
  );
  const [selectedVrpBatchId, setSelectedVrpBatchId] = useState<string | null>(
    initialRoute.vrpBatchId
  );
  const [reviewOrigin, setReviewOrigin] = useState<"documents" | "vrp">(
    "documents"
  );
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);
  const [stockMode, setStockMode] = useState<"receive" | "correct" | null>(null);
  const [receivingDialogMode, setReceivingDialogMode] =
    useState<ReceiveMode | null>(null);

  const permissions = session.user.permissions ?? [];
  const can = (permission: string) => permissions.includes(permission);
  const navigateTo = useCallback(
    (
      view: WorkspaceView,
      options: {
        documentId?: string | null;
        vrpBatchId?: string | null;
        identityTab?: IdentityTab;
        settingsAi?: boolean;
        settingsReports?: boolean;
        replace?: boolean;
      } = {}
    ) => {
      const next: RouteState = {
        view,
        documentId: options.documentId ?? null,
        vrpBatchId: options.vrpBatchId ?? null,
        identityTab: options.identityTab ?? identityTab,
        settingsAi: options.settingsAi ?? false,
        settingsReports: options.settingsReports ?? false
      };
      setActiveView(next.view);
      setSelectedDocumentId(next.documentId);
      setSelectedVrpBatchId(next.vrpBatchId);
      setIdentityTab(next.identityTab);
      setSettingsAi(next.settingsAi);
      setSettingsReports(next.settingsReports);
      setMobileMoreOpen(false);
      const nextPath = routePath(next);
      if (`${window.location.pathname}${window.location.search}` !== nextPath) {
        window.history[options.replace ? "replaceState" : "pushState"](
          {},
          "",
          nextPath
        );
      }
    },
    [identityTab]
  );

  useEffect(() => {
    window.history.replaceState({}, "", routePath(initialRoute));
    const handlePopState = () => {
      const next = readRoute(locked);
      setActiveView(next.view);
      setSelectedDocumentId(next.documentId);
      setSelectedVrpBatchId(next.vrpBatchId);
      setIdentityTab(next.identityTab);
      setSettingsAi(next.settingsAi);
      setSettingsReports(next.settingsReports);
      setMobileMoreOpen(false);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [initialRoute, locked]);
  const productsQuery = useQuery({
    queryKey: ["products"],
    queryFn: getProducts,
    enabled: !locked && can("products.read")
  });
  const stockQuery = useQuery({
    queryKey: ["stock"],
    queryFn: getStock,
    enabled: !locked && can("stock.read"),
    refetchInterval: activeView === "products" ? 5000 : false
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
              onClick={() => navigateTo("overview")}
            >
              <LayoutDashboard aria-hidden="true" />
              Áttekintés
            </button>
          )}
          {!locked && can("inventory.count") && (
            <button
              className={`nav-item ${activeView === "inventory" ? "active" : ""}`}
              onClick={() => navigateTo("inventory")}
            >
              <ClipboardList aria-hidden="true" />
              Kézi leltár
            </button>
          )}
          {!locked && can("products.read") && (
            <button
              className={`nav-item ${activeView === "products" ? "active" : ""}`}
              onClick={() => navigateTo("products")}
            >
              <Barcode aria-hidden="true" />
              Termékek
            </button>
          )}
          {!locked && can("documents.read") && (
            <button
              className={`nav-item ${
                ["documents", "uploads", "reviews", "receipt"].includes(activeView)
                  ? "active"
                  : ""
              }`}
              onClick={() => navigateTo("documents")}
            >
              <FileText aria-hidden="true" />
              Dokumentumok
            </button>
          )}
          {!locked && can("vrp.read") && (
            <button
              className={`nav-item ${activeView === "vrp" ? "active" : ""}`}
              onClick={() => {
                setSelectedVrpBatchId(null);
                navigateTo("vrp");
              }}
            >
              <FileSpreadsheet aria-hidden="true" />
              VRP-import
            </button>
          )}
          {!locked && can("email.read") && (
            <button
              className={`nav-item ${activeView === "email" ? "active" : ""}`}
              onClick={() => navigateTo("email")}
            >
              <Mail aria-hidden="true" />
              E-mail postafiók
            </button>
          )}
          {!locked && can("plugins.read") && (
            <button
              className={`nav-item ${activeView === "plugins" ? "active" : ""}`}
              onClick={() => navigateTo("plugins")}
            >
              <Puzzle aria-hidden="true" />
              Pluginok
            </button>
          )}
          <button
            className={`nav-item ${activeView === "identity" ? "active" : ""}`}
            onClick={() => navigateTo("identity", { identityTab: "users" })}
          >
            <UserCog aria-hidden="true" />
            Felhasználók és biztonság
          </button>
        </nav>
        <div className="sidebar-footer">
          {!locked && (
            <button
              className={`nav-item ${activeView === "settings" ? "active" : ""}`}
              onClick={() => navigateTo("settings")}
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
              focusAi={settingsAi}
              focusReports={settingsReports}
              onNavigate={(target) => {
                if (target === "reports") {
                  navigateTo("settings", { settingsReports: true });
                } else {
                  navigateTo(target);
                }
              }}
            />
          </Suspense>
        ) : activeView === "identity" ? (
          <Suspense fallback={<div className="empty-state">Identity betöltése…</div>}>
            <IdentityPage
              key={identityTab}
              session={session}
              onSessionUpdated={onSessionUpdated}
              initialTab={identityTab}
              onTabChange={(tab) => {
                setIdentityTab(tab);
                navigateTo("identity", { identityTab: tab });
              }}
            />
          </Suspense>
        ) : ["documents", "uploads", "reviews"].includes(activeView) ? (
          <div className="document-workspace">
            <header className="workspace-header document-workspace-header">
              <div>
                <p className="eyebrow">Bejövő bizonylatok</p>
                <h1>Dokumentumok</h1>
                <p className="page-lead">
                  Beérkezés, folytatható feltöltés és ellenőrzés egy munkatérben.
                </p>
              </div>
            </header>
            <nav className="document-workspace-tabs" aria-label="Dokumentumterületek">
              {can("documents.read") && (
                <button
                  className={activeView === "documents" ? "active" : ""}
                  onClick={() => navigateTo("documents")}
                >
                  <FileText aria-hidden="true" />
                  Beérkezett
                </button>
              )}
              {(can("documents.upload") || can("vrp.upload")) && (
                <button
                  className={activeView === "uploads" ? "active" : ""}
                  onClick={() => navigateTo("uploads")}
                >
                  <CloudUpload aria-hidden="true" />
                  Feltöltés alatt
                </button>
              )}
              {can("reviews.read") && (
                <button
                  className={activeView === "reviews" ? "active" : ""}
                  onClick={() => {
                    setReviewOrigin("documents");
                    navigateTo("reviews");
                  }}
                >
                  <FileSearch aria-hidden="true" />
                  Ellenőrzendő
                </button>
              )}
            </nav>
            {activeView === "uploads" ? (
              <Suspense fallback={<div className="empty-state">Feltöltési sor betöltése…</div>}>
                <UploadQueuePage
                  embedded
                  organizationId={session.user.organization_id}
                  permissions={permissions}
                  onOpenResult={(upload) => {
                    if (upload.result_entity_type === "vrp_import_batch") {
                      navigateTo("vrp", { vrpBatchId: upload.result_entity_id });
                    } else {
                      navigateTo("documents");
                    }
                  }}
                />
              </Suspense>
            ) : activeView === "reviews" ? (
              <ReviewTasksPage
                embedded
                onBack={() => navigateTo(reviewOrigin)}
                onOpenReceipt={(documentId) =>
                  navigateTo("receipt", { documentId })
                }
                onOpenVrp={(batchId) =>
                  navigateTo("vrp", { vrpBatchId: batchId })
                }
              />
            ) : (
              <DocumentsPage
                embedded
                onUpload={() => navigateTo("uploads")}
                onOpenReviews={() => {
                  setReviewOrigin("documents");
                  navigateTo("reviews");
                }}
                onOpenReceipt={(documentId) =>
                  navigateTo("receipt", { documentId })
                }
              />
            )}
          </div>
        ) : activeView === "receipt" && selectedDocumentId ? (
          <ReceiptReviewPage
            documentId={selectedDocumentId}
            products={products}
            canReverse={can("stock.reverse")}
            onBack={() => navigateTo("documents")}
          />
        ) : activeView === "vrp" ? (
          <VrpImportsPage
            role={session.user.role}
            products={products}
            initialBatchId={selectedVrpBatchId}
            onOpenReviews={() => {
              setReviewOrigin("vrp");
              navigateTo("reviews");
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
        ) : activeView === "products" ? (
          <Suspense fallback={<div className="empty-state">Termékek betöltése…</div>}>
            <ProductsPage
              products={products}
              stock={stock}
              loading={loading}
              failed={failed}
              permissions={permissions}
              onNewProduct={() => setProductDialog(true)}
              onReceive={(mode) => setReceivingDialogMode(mode)}
            />
          </Suspense>
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
                    onClick={() => navigateTo("inventory")}
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
                    onClick={() => navigateTo("uploads")}
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

      <nav className="mobile-actions primary-mobile-nav" aria-label="Mobil navigáció">
        {!locked && can("stock.read") && (
          <button
            className={activeView === "overview" ? "accent" : ""}
            onClick={() => navigateTo("overview")}
          >
            <Home aria-hidden="true" />
            Kezdő
          </button>
        )}
        {!locked && can("products.read") && (
          <button
            className={activeView === "products" ? "accent" : ""}
            onClick={() => navigateTo("products")}
          >
            <Barcode aria-hidden="true" />
            Termékek
          </button>
        )}
        {!locked && can("stock.receive") && (
          <button
            className="mobile-receive-action"
            onClick={() => {
              if (
                can("documents.upload") &&
                can("documents.process") &&
                can("receipts.confirm")
              ) {
                setReceivingDialogMode("delivery_note");
              } else {
                setStockMode("receive");
              }
            }}
          >
            <PackagePlus aria-hidden="true" />
            Bevételezés
          </button>
        )}
        {!locked && can("inventory.count") && (
          <button
            className={activeView === "inventory" ? "accent" : ""}
            onClick={() => navigateTo("inventory")}
          >
            <ClipboardList aria-hidden="true" />
            Leltár
          </button>
        )}
        <button
          className={
            !["overview", "products", "inventory"].includes(activeView)
              ? "accent"
              : ""
          }
          onClick={() => setMobileMoreOpen(true)}
        >
          <MoreHorizontal aria-hidden="true" />
          Több
        </button>
      </nav>

      <Dialog.Root open={mobileMoreOpen} onOpenChange={setMobileMoreOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="mobile-more-overlay" />
          <Dialog.Content className="mobile-more-sheet">
            <div className="mobile-more-heading">
              <div>
                <p className="section-label">Navigáció</p>
                <Dialog.Title>További területek</Dialog.Title>
              </div>
              <Dialog.Close className="icon-button" aria-label="Bezárás">
                <X aria-hidden="true" />
              </Dialog.Close>
            </div>
            <div className="mobile-more-grid">
              {!locked && can("documents.read") && (
                <button onClick={() => navigateTo("documents")}>
                  <FileText aria-hidden="true" />
                  <span>
                    <strong>Dokumentumok</strong>
                    <small>Beérkezés, feltöltés, ellenőrzés</small>
                  </span>
                </button>
              )}
              {!locked && can("vrp.read") && (
                <button onClick={() => navigateTo("vrp")}>
                  <FileSpreadsheet aria-hidden="true" />
                  <span>
                    <strong>VRP-import</strong>
                    <small>Riportok és automatizálás</small>
                  </span>
                </button>
              )}
              {!locked && can("email.read") && (
                <button onClick={() => navigateTo("email")}>
                  <Mail aria-hidden="true" />
                  <span>
                    <strong>E-mail</strong>
                    <small>Bejövő bizonylatok</small>
                  </span>
                </button>
              )}
              {!locked && can("plugins.read") && (
                <button onClick={() => navigateTo("plugins")}>
                  <Puzzle aria-hidden="true" />
                  <span>
                    <strong>Pluginok</strong>
                    <small>Bővítmények kezelése</small>
                  </span>
                </button>
              )}
              <button
                onClick={() => navigateTo("identity", { identityTab: "users" })}
              >
                <UserCog aria-hidden="true" />
                <span>
                  <strong>Felhasználók és biztonság</strong>
                  <small>Szerepkörök, MFA, API-tokenek</small>
                </span>
              </button>
              {!locked && (
                <button onClick={() => navigateTo("settings")}>
                  <Settings aria-hidden="true" />
                  <span>
                    <strong>Beállítások</strong>
                    <small>AI-kulcs és rendszerbeállítások</small>
                  </span>
                </button>
              )}
            </div>
            <button className="mobile-more-logout" onClick={onLogout}>
              <LogOut aria-hidden="true" />
              Kijelentkezés
            </button>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

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
        {receivingDialogMode ? (
          <ProductReceivingDialog
            key={receivingDialogMode}
            open
            initialMode={receivingDialogMode}
            products={products}
            stock={stock}
            permissions={permissions}
            onOpenChange={(open) => !open && setReceivingDialogMode(null)}
          />
        ) : null}
      </Suspense>
    </div>
  );
}
