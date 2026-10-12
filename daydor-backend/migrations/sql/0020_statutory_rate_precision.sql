-- Finding 18 (docs/model-findings.md): every numeric column in the generated DDL is
-- numeric(14,2) (daydor.model.ddl.SQL_TYPE's blanket mapping), which is correct for currency
-- amounts but silently rounds statutory rate *fractions* to the nearest 0.01 -- a real FICA rate
-- of 0.0765 (7.65%) is stored as 0.08, a ~4.6% relative error in a legally mandated withholding.
-- Caught by a test asserting an exact computed amount, not by inspection.
--
-- Widens employee_rate/employer_rate specifically (not every numeric column -- wage_ceiling and
-- every currency-amount column elsewhere are correctly 2dp) to numeric(8,6), enough headroom for
-- any realistic statutory rate. A documented deviation from the generated DDL, same pattern as
-- 0012_hire.sql's nullable PII columns; not a daydor.model.ddl change (rates vs. amounts would
-- need their own physical-type distinction in the model to generate correctly, which is a
-- model/artifact change, not a generator bug to silently paper over here).
ALTER TABLE public.statutory_rate_rule ALTER COLUMN employee_rate TYPE numeric(8,6);
ALTER TABLE public.statutory_rate_rule ALTER COLUMN employer_rate TYPE numeric(8,6);
