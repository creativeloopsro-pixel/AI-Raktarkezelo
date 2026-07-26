import { useDeferredValue, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  Barcode,
  Boxes,
  FileUp,
  PackageCheck,
  PackagePlus,
  Plus,
  Search
} from "lucide-react";

import type { Product, StockBalance } from "../types";
import EanBarcode from "./EanBarcode";

type ReceiveMode = "delivery_note" | "barcode";

type Props = {
  products: Product[];
  stock: StockBalance[];
  loading: boolean;
  failed: boolean;
  permissions: string[];
  onNewProduct: () => void;
  onReceive: (mode: ReceiveMode) => void;
};

const formatter = new Intl.NumberFormat("hu-HU", {
  maximumFractionDigits: 3
});

export default function ProductsPage({
  products,
  stock,
  loading,
  failed,
  permissions,
  onNewProduct,
  onReceive
}: Props) {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const can = (permission: string) => permissions.includes(permission);
  const canCreate = can("products.write");
  const canReceive = can("stock.receive");
  const canUseDeliveryAi =
    can("documents.upload") &&
    can("documents.process") &&
    can("receipts.confirm") &&
    canReceive;

  const stockByProductId = useMemo(
    () => new Map(stock.map((item) => [item.product_id, item])),
    [stock]
  );
  const filteredProducts = useMemo(() => {
    const needle = deferredSearch.trim().toLocaleLowerCase("hu");
    if (!needle) return products;
    return products.filter(
      (product) =>
        product.name.toLocaleLowerCase("hu").includes(needle) ||
        product.internal_sku.toLocaleLowerCase("hu").includes(needle) ||
        product.barcodes.some((barcode) => barcode.code.includes(needle))
    );
  }, [deferredSearch, products]);

  const eanMissing = products.filter(
    (product) => !product.barcodes.some((barcode) => barcode.is_primary)
  ).length;
  const stocked = stock.filter((item) => Number(item.quantity) > 0).length;
  const lowStock = stock.filter(
    (item) => Number(item.quantity) <= Number(item.min_stock)
  ).length;

  return (
    <motion.div
      className="products-page"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <header className="workspace-header products-header">
        <div>
          <p className="eyebrow">Terméktörzs és bevételezés</p>
          <h1>Termékek</h1>
        </div>
        <div className="header-actions always-visible products-actions">
          {canReceive ? (
            <button
              className="secondary-button"
              onClick={() => onReceive("barcode")}
            >
              <Plus aria-hidden="true" />
              Készlet hozzáadása
            </button>
          ) : null}
          {canUseDeliveryAi ? (
            <button
              className="secondary-button"
              onClick={() => onReceive("delivery_note")}
            >
              <FileUp aria-hidden="true" />
              Szállítólevélről
            </button>
          ) : null}
          {canCreate ? (
            <button className="primary-button" onClick={onNewProduct}>
              <PackagePlus aria-hidden="true" />
              Új termék
            </button>
          ) : null}
        </div>
      </header>

      <section className="product-summary" aria-label="Termékmutatók">
        <div>
          <Boxes aria-hidden="true" />
          <span>Összes termék</span>
          <strong>{formatter.format(products.length)}</strong>
        </div>
        <div>
          <PackageCheck aria-hidden="true" />
          <span>Van készleten</span>
          <strong>{formatter.format(stocked)}</strong>
        </div>
        <div className={lowStock ? "attention" : ""}>
          <AlertTriangle aria-hidden="true" />
          <span>Minimum alatt</span>
          <strong>{formatter.format(lowStock)}</strong>
        </div>
        <div className={eanMissing ? "attention" : ""}>
          <Barcode aria-hidden="true" />
          <span>EAN nélkül</span>
          <strong>{formatter.format(eanMissing)}</strong>
        </div>
      </section>

      <section className="products-list-section">
        <div className="section-heading product-list-heading">
          <div>
            <p className="section-label">Katalógus</p>
            <h2>Termékek és aktuális készlet</h2>
          </div>
          <label className="search-field">
            <Search aria-hidden="true" />
            <span className="sr-only">Termék keresése</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Név, SKU vagy EAN"
            />
          </label>
        </div>

        {loading ? (
          <div className="empty-state">Termékek betöltése…</div>
        ) : null}
        {failed ? (
          <div className="empty-state error-state">
            <AlertTriangle aria-hidden="true" />
            A termékadatok most nem érhetők el.
          </div>
        ) : null}
        {!loading && !failed && filteredProducts.length === 0 ? (
          <div className="empty-state">
            <Boxes aria-hidden="true" />
            <strong>
              {products.length ? "Nincs találat." : "Még nincs termék."}
            </strong>
            <span>
              {products.length
                ? "Próbálj másik nevet, SKU-t vagy EAN-kódot."
                : "Az első terméket az Új termék gombbal hozhatod létre."}
            </span>
          </div>
        ) : null}
        {!loading && !failed && filteredProducts.length > 0 ? (
          <div className="product-table-wrap">
            <table className="product-table">
              <thead>
                <tr>
                  <th>Termék</th>
                  <th>Elsődleges EAN</th>
                  <th>SKU</th>
                  <th>Állapot</th>
                  <th className="numeric">Készlet</th>
                  <th className="numeric">Minimum</th>
                </tr>
              </thead>
              <tbody>
                {filteredProducts.map((product) => {
                  const balance = stockByProductId.get(product.id);
                  const quantity = Number(balance?.quantity ?? 0);
                  const minimum = Number(product.min_stock);
                  const low = quantity <= minimum;
                  const primaryBarcode =
                    product.barcodes.find((barcode) => barcode.is_primary)
                      ?.code ??
                    product.barcodes[0]?.code ??
                    null;
                  return (
                    <tr key={product.id}>
                      <td>
                        <strong>{product.name}</strong>
                        <small>{product.base_unit}</small>
                      </td>
                      <td>
                        <EanBarcode code={primaryBarcode} compact />
                      </td>
                      <td className="muted-text">{product.internal_sku}</td>
                      <td>
                        <span className={`status-dot ${low ? "warning" : ""}`}>
                          {low ? "Minimum alatt" : "Rendben"}
                        </span>
                      </td>
                      <td className="numeric quantity-cell">
                        {formatter.format(quantity)}
                      </td>
                      <td className="numeric muted-text">
                        {formatter.format(minimum)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </motion.div>
  );
}
