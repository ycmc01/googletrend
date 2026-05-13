如何填寫 apple_revenue_weights.csv
=================================

每一列填一個會計季 (Apple 會計年度 9 月底結束)。
數字填「該 segment 當季營收 (USD millions)」，不是百分比 — 程式會自動轉佔比。

資料來源：Apple 10-Q (Q1/Q2/Q3) / 10-K (Q4) 「Net sales by category」
官方位置：https://investor.apple.com/sec-filings/
快速查表：https://www.apple.com/newsroom/  -> 找 quarterly results press release，
        通常會直接列 product category 的營收

範例 (Q4 FY2024, 截至 2024-09-28)：
  iPhone:     46,222
  Mac:        7,744
  iPad:       6,950
  Wearables:  9,042
  Services:   24,972
  total_revenue_usd_m: 94,930

注意：
- 數字用百萬美元，不要逗號
- total_revenue_usd_m 應等於 5 個 segment 加總 (有時略有出入，以 10-Q 公告為準)
- source_filing 欄位填 "10-Q FY24Q4" 或檔案 URL 即可，方便回溯

填完後執行：
  python scripts/compute_gits.py
就會自動讀取並轉成 segment 權重 time-series。
