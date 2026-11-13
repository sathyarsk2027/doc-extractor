import { useState } from "react";
import { LineItemsTable } from "./LineItemsTable";
import { FlagMessage } from "./FlagMessage";
import { isFieldChanged } from "../utils/diff";

export function ReviewForm({
  formData,
  originalData = {},
  flags = {},
  onFieldChange,
  onNumericChange,
  rawNumeric = {},
  onNumericValidityChange,
}) {
  const [showGst, setShowGst] = useState(false);
  const isChanged = (f) => isFieldChanged(originalData[f], formData[f]);
  const isDateIso = /^\d{4}-\d{2}-\d{2}$/.test(formData.date || "");

  return (
    <div className="form-pane card">
      <div className="form-grid">
        <div className="form-group">
          <label htmlFor="vendor">
            Vendor {isChanged("vendor") && <span className="diff-marker" title="Changed from AI">●</span>}
          </label>
          <input
            id="vendor"
            type="text"
            className={flags["vendor"] ? "input-flagged" : ""}
            value={formData.vendor}
            onChange={(e) => onFieldChange("vendor", e.target.value)}
          />
          <FlagMessage flag={flags["vendor"]} />
        </div>

        <div className="form-group">
          <label htmlFor="invoice_number">
            Invoice # {isChanged("invoice_number") && <span className="diff-marker" title="Changed from AI">●</span>}
          </label>
          <input
            id="invoice_number"
            type="text"
            className={flags["invoice_number"] ? "input-flagged" : ""}
            value={formData.invoice_number}
            onChange={(e) => onFieldChange("invoice_number", e.target.value)}
          />
          <FlagMessage flag={flags["invoice_number"]} />
        </div>

        <div className="form-group">
          <label htmlFor="date">
            Invoice Date {isChanged("date") && <span className="diff-marker" title="Changed from AI">●</span>}
          </label>
          <input
            id="date"
            type={isDateIso ? "date" : "text"}
            className={flags["date"] ? "input-flagged" : ""}
            value={formData.date}
            onChange={(e) => onFieldChange("date", e.target.value)}
          />
          <FlagMessage flag={flags["date"]} />
        </div>

        <div className="form-group">
          <label htmlFor="currency">
            Currency {isChanged("currency") && <span className="diff-marker" title="Changed from AI">●</span>}
          </label>
          <input
            id="currency"
            type="text"
            maxLength={4}
            className={flags["currency"] ? "input-flagged" : ""}
            value={formData.currency}
            onChange={(e) => onFieldChange("currency", e.target.value.toUpperCase())}
          />
          <FlagMessage flag={flags["currency"]} />
        </div>

        <div className="form-group">
          <label htmlFor="subtotal">
            Subtotal {isChanged("subtotal") && <span className="diff-marker" title="Changed from AI">●</span>}
          </label>
          <input
            id="subtotal"
            type="text"
            inputMode="decimal"
            className={flags["subtotal"] ? "input-flagged" : ""}
            value={rawNumeric.subtotal !== undefined ? rawNumeric.subtotal : (formData.subtotal ?? "")}
            onChange={(e) => onNumericChange("subtotal", e.target.value)}
          />
          <FlagMessage flag={flags["subtotal"]} />
        </div>

        <div className="form-group">
          <label htmlFor="tax">
            Tax {isChanged("tax") && <span className="diff-marker" title="Changed from AI">●</span>}
          </label>
          <input
            id="tax"
            type="text"
            inputMode="decimal"
            className={flags["tax"] ? "input-flagged" : ""}
            value={rawNumeric.tax !== undefined ? rawNumeric.tax : (formData.tax ?? "")}
            onChange={(e) => onNumericChange("tax", e.target.value)}
          />
          <FlagMessage flag={flags["tax"]} />
        </div>

        <div className="form-group full-width">
          <label htmlFor="total">
            Total {isChanged("total") && <span className="diff-marker" title="Changed from AI">●</span>}
          </label>
          <input
            id="total"
            type="text"
            inputMode="decimal"
            className={flags["total"] ? "input-flagged" : ""}
            value={rawNumeric.total !== undefined ? rawNumeric.total : (formData.total ?? "")}
            onChange={(e) => onNumericChange("total", e.target.value)}
          />
          <FlagMessage flag={flags["total"]} />
        </div>
      </div>

      <div className="collapsible-section">
        <button type="button" className="collapsible-trigger" onClick={() => setShowGst(!showGst)}>
          <span>{showGst ? "▼ Hide GST & Tax Breakdown" : "▶ Show GST & Tax Breakdown"}</span>
        </button>
        {showGst && (
          <div className="gst-grid">
            {[
              { id: "taxable_amount", label: "Taxable Amount" },
              { id: "cgst", label: "CGST" },
              { id: "sgst", label: "SGST" },
              { id: "igst", label: "IGST" },
              { id: "cess", label: "Cess" },
            ].map(({ id, label }) => (
              <div key={id} className="form-group">
                <label htmlFor={id}>{label}</label>
                <input
                  id={id}
                  type="text"
                  inputMode="decimal"
                  value={rawNumeric[id] !== undefined ? rawNumeric[id] : (formData[id] ?? "")}
                  onChange={(e) => onNumericChange(id, e.target.value)}
                />
              </div>
            ))}
            <div className="form-group checkbox-group">
              <label htmlFor="prices_include_tax">
                <input
                  id="prices_include_tax"
                  type="checkbox"
                  checked={Boolean(formData.prices_include_tax)}
                  onChange={(e) => onFieldChange("prices_include_tax", e.target.checked)}
                />
                Prices include tax
              </label>
            </div>
          </div>
        )}
      </div>

      <LineItemsTable
        items={formData.line_items || []}
        originalItems={originalData.line_items || []}
        flags={flags}
        onChange={(newItems) => onFieldChange("line_items", newItems)}
        onNumericValidityChange={onNumericValidityChange}
      />
    </div>
  );
}
