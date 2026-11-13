import { Fragment } from "react";
import { FlagMessage } from "./FlagMessage";
import { isFieldChanged } from "../utils/diff";

export function LineItemsTable({
  items = [],
  originalItems = [],
  flags = {},
  onChange,
  onNumericValidityChange,
}) {
  const handleItemChange = (index, field, value) => {
    const updated = [...items];
    const current = { ...updated[index] };

    if (field === "description") {
      current.description = value;
    } else {
      // Decimal inputs: validate format
      if (value === "") {
        current[field] = null;
        current[`_${field}_raw`] = "";
      } else {
        current[`_${field}_raw`] = value;
        const parsed = parseFloat(value);
        if (!isNaN(parsed) && isFinite(parsed)) {
          current[field] = parsed;
        }
      }
    }

    updated[index] = current;
    onChange(updated);

    // Validate all numeric fields across items
    let hasInvalid = false;
    updated.forEach((it) => {
      ["quantity", "unit_price", "amount"].forEach((numField) => {
        const raw = it[`_${numField}_raw`];
        if (raw !== undefined && raw !== "" && (isNaN(Number(raw)) || isNaN(parseFloat(raw)))) {
          hasInvalid = true;
        }
      });
    });
    if (onNumericValidityChange) onNumericValidityChange(hasInvalid);
  };

  const handleAddRow = () => {
    const updated = [
      ...items,
      { description: "", quantity: 1, unit_price: null, amount: null },
    ];
    onChange(updated);
  };

  const handleDeleteRow = (index) => {
    const updated = items.filter((_, i) => i !== index);
    onChange(updated);
  };

  const isRowFieldChanged = (index, field) => {
    if (!originalItems || !originalItems[index]) return true; // new row
    return isFieldChanged(originalItems[index][field], items[index][field]);
  };

  return (
    <div className="line-items-section">
      <div className="section-header">
        <h3>Line Items ({items.length})</h3>
        <button
          type="button"
          className="btn btn-secondary btn-small"
          onClick={handleAddRow}
        >
          + Add Row
        </button>
      </div>

      {flags["line_items"] && <FlagMessage flag={flags["line_items"]} />}

      {items.length === 0 ? (
        <div className="empty-items-note">
          <p>No line items extracted. Click &quot;+ Add Row&quot; to add items manually.</p>
        </div>
      ) : (
        <div className="table-responsive">
          <table className="line-items-table">
            <thead>
              <tr>
                <th style={{ width: "45%" }}>Description</th>
                <th style={{ width: "15%" }}>Qty</th>
                <th style={{ width: "18%" }}>Unit Price</th>
                <th style={{ width: "18%" }}>Amount</th>
                <th style={{ width: "4%" }} aria-label="Actions"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => {
                const amountFlag = flags[`line_items[${idx}].amount`];
                const mathFlag = flags[`line_items[${idx}].math`];
                const rowFlag = amountFlag || mathFlag;

                return (
                  <Fragment key={idx}>
                    <tr className={rowFlag ? "row-flagged" : ""}>
                      <td>
                        <div className="cell-input-group">
                          <input
                            type="text"
                            aria-label={`Item ${idx + 1} Description`}
                            value={item.description || ""}
                            placeholder="Description"
                            onChange={(e) => handleItemChange(idx, "description", e.target.value)}
                          />
                          {isRowFieldChanged(idx, "description") && (
                            <span className="diff-marker" title="Changed from AI">●</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <div className="cell-input-group">
                          <input
                            type="text"
                            inputMode="decimal"
                            aria-label={`Item ${idx + 1} Quantity`}
                            value={item._quantity_raw !== undefined ? item._quantity_raw : (item.quantity ?? "")}
                            placeholder="0"
                            onChange={(e) => handleItemChange(idx, "quantity", e.target.value)}
                          />
                          {isRowFieldChanged(idx, "quantity") && (
                            <span className="diff-marker" title="Changed from AI">●</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <div className="cell-input-group">
                          <input
                            type="text"
                            inputMode="decimal"
                            aria-label={`Item ${idx + 1} Unit Price`}
                            value={item._unit_price_raw !== undefined ? item._unit_price_raw : (item.unit_price ?? "")}
                            placeholder="0.00"
                            onChange={(e) => handleItemChange(idx, "unit_price", e.target.value)}
                          />
                          {isRowFieldChanged(idx, "unit_price") && (
                            <span className="diff-marker" title="Changed from AI">●</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <div className="cell-input-group">
                          <input
                            type="text"
                            inputMode="decimal"
                            aria-label={`Item ${idx + 1} Amount`}
                            className={amountFlag ? "input-flagged" : ""}
                            value={item._amount_raw !== undefined ? item._amount_raw : (item.amount ?? "")}
                            placeholder="0.00"
                            onChange={(e) => handleItemChange(idx, "amount", e.target.value)}
                          />
                          {isRowFieldChanged(idx, "amount") && (
                            <span className="diff-marker" title="Changed from AI">●</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn-icon-danger"
                          title="Delete line item"
                          aria-label={`Delete line item ${idx + 1}`}
                          onClick={() => handleDeleteRow(idx)}
                        >
                          ✕
                        </button>
                      </td>
                    </tr>
                    {rowFlag && (
                      <tr className="line-item-flag-row">
                        <td colSpan={5} className="line-item-flag-cell">
                          <FlagMessage flag={rowFlag} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
