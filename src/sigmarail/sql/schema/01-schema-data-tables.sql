-- Removed CREATE DATABASE and USE statements; Database context provided by client connection.

-- =============================================================================
-- Sharadar Table Definitions (Sharadar source-table definitions)
-- =============================================================================

-- TICKERS: Sharadar TICKERS Table
-- This table serves as a central metadata repository for all securities in the Sharadar dataset.
-- It provides essential reference information such as permanent and current ticker symbols, company names, exchange listings,
-- industry classifications (SIC, Fama, GICS-like), and status indicators (e.g., isdelisted).
-- It also links tickers to their respective data across other Sharadar tables (like SF1 for fundamentals, SEP for prices) and external resources (SEC filings, company websites).
CREATE TABLE IF NOT EXISTS tickers
(
    `table` String COMMENT 'Table: Retail Sharadar table id (stocks, funds, fundamentals, …). Route prices via stocks vs funds, not ticker string alone.',
    `permaticker` String COMMENT 'Permanent Ticker Symbol: The permaticker is a unique and unchanging identifier for an issuer in the dataset which we as the data provider issue. This field is not included in other tables in order to maximise data scalability in those tables.',
    `ticker` LowCardinality(String) COMMENT 'Ticker Symbol: The ticker is a unique identifier for a security in the database. Where a company is delisted and the ticker subsequently recycled for use by a different company, we utilise that ticker for the currently active company and append a number to the ticker of the delisted company. The ACTIONS table provides a record of historical ticker changes.',
    `name` String COMMENT 'Issuer Name: The name of the security issuer.',
    `exchange` LowCardinality(String) COMMENT 'Stock Exchange: The exchange on which the security\'s primary listing is held. Examples are: ',
    `isdelisted` String COMMENT 'Is Delisted?: Is the security delisted? [Y]es or [N]o.',
    `category` LowCardinality(String) COMMENT 'Issuer Category: The category of the issuer: Domestic, Canadian or ADR. This field is based on the filing category with the SEC. Domestic firms file form 10, ADRs file form 20 and Canadian firms file form 40.',
    `cusips` String COMMENT 'CUSIPs: A security identifier. Space delimited in the event of multiple identifiers.',
    `figi` String DEFAULT '' COMMENT 'FIGI: OpenFIGI identifier when provided by Sharadar retail tickers.',
    `siccode` String COMMENT 'Standard Industrial Classification (SIC) Code: The Standard Industrial Classification (SIC) is a system for classifying industries by a four-digit code, as sourced from SEC filings. More on the SIC system here: https://en.wikipedia.org/wiki/Standard_Industrial_Classification ',
    `sicsector` String COMMENT 'SIC Sector: The SIC sector is based on the SIC code and the division tabled here: https://en.wikipedia.org/wiki/Standard_Industrial_Classification ',
    `sicindustry` String COMMENT 'SIC Industry: The SIC industry is based on the SIC code and the industry tabled here: https://www.sec.gov/info/edgar/siccodes.htm',
    `famaindustry` String COMMENT 'Fama Industry: Industry classifications based on the SIC code and classifications by Fama and French here: http://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_48_ind_port.html',
    `sector` String COMMENT 'Sector: A sector classification based on SIC codes in a format which approximates to GICS.',
    `industry` String COMMENT 'Industry: An industry classification based on SIC codes in a format which approximates to GICS.',
    `scalemarketcap` String COMMENT 'Company Scale - Market Cap: This field is experimental and subject to change. It categorises the company according to it\'s maximum observed market cap as follows: 1 - Nano <$50m, 2 - Micro < $300m, 3 - Small < $2bn, 4 - Mid <$10bn, 5 - Large < $200bn, 6 - Mega >= $200bn',
    `scalerevenue` String COMMENT 'Company Scale - Revenue: This field is experimental and subject to change. It categorises the company according to it\'s maximum observed annual revenue as follows: 1 - Nano <$50m, 2 - Micro < $300m, 3 - Small < $2bn, 4 - Mid <$10bn, 5 - Large < $200bn, 6 - Mega >= $200bn',
    `relatedtickers` String COMMENT 'Related Tickers: Where related tickers have been identified this field is populated. Related tickers can include the prior ticker before a ticker change, and it includes tickers for alternative share classes.',
    `currency` String COMMENT 'Currency: The company functional reporting currency for the SF1 Fundamentals table or the currency for EOD prices in SEP and SFP.',
    `location` String COMMENT 'Location: The company location as registered with the Securities and Exchange Commission.',
    `lastupdated` DateTime('America/New_York') DEFAULT toDateTime(concat(toString(today()), ' 23:59:59'), 'America/New_York') COMMENT 'Last Updated DateTime: Automatically set to end-of-day for real-time data support.',
    `firstadded` String COMMENT 'First Added Date: The date that the ticker was first added to coverage in the dataset.',
    `firstpricedate` String COMMENT 'First Price Date: The date of the first price observation for a given ticker. Can be used as a proxy for IPO date. Minimum value of 1986-01-01 for IPO\'s that occurred prior to this date. Note: this does not necessarily represent the first price date available in our datasets since our end of day price history currently starts in December 1998.',
    `lastpricedate` String COMMENT 'Last Price Date: The most recent price observation available.',
    `firstquarter` String COMMENT 'First Quarter: The first financial quarter available in the dataset.',
    `lastquarter` String COMMENT 'Last Quarter: The last financial quarter available in the dataset.',
    `secfilings` String COMMENT 'SEC Filings URL: The URL pointing to the SEC filings which also contains the Central Index Key (CIK).',
    `companysite` String COMMENT 'Company Website URL: The URL pointing to the company website.'
)
ENGINE = ReplacingMergeTree(lastupdated)
ORDER BY (permaticker)
SETTINGS index_granularity = 8192
COMMENT 'Central metadata for all securities. Provides ticker symbols, company names, exchange, industry classifications, and status. Sourced from Sharadar TICKERS table.';

-- SEP: Sharadar Equity Prices Table
-- This table stores end-of-day (EOD) price and volume data for publicly traded equities (common stock, warrants, preferred stock).
-- It includes unadjusted prices, split-adjusted prices, and prices fully adjusted for splits, cash dividends, and spinoffs.
CREATE TABLE IF NOT EXISTS sep
(
    `ticker` LowCardinality(String) COMMENT 'Ticker Symbol: The ticker is a unique identifier for a security in the database. Where a company is delisted and the ticker subsequently recycled for use by a different company, we utilise that ticker for the currently active company and append a number to the ticker of the delisted company. The ACTIONS table provides a record of historical ticker changes.',
    `date` Date COMMENT 'Price Date: The trade date of the price observations.',
    `open` Float64 COMMENT 'Open Price - Split Adjusted: The official exchange opening price, adjusted for stock splits and stock dividends. Not adjusted for cash dividends or spinoffs.',
    `high` Float64 COMMENT 'High Price - Split Adjusted: The high share price, adjusted for stock splits and stock dividends. Not adjusted for cash dividends or spinoffs.',
    `low` Float64 COMMENT 'Low Price - Split Adjusted: The low share price, adjusted for stock splits and stock dividends. Not adjusted for cash dividends or spinoffs.',
    `close` Float64 COMMENT 'Close Price - Split Adjusted: The official exchange close price, adjusted for stock splits and stock dividends. Not adjusted for cash dividends or spinoffs.',
    `volume` Float64 COMMENT 'Volume - Split Adjusted: The daily traded volume across all exchanges, adjusted for stock splits and stock dividends. Not adjusted for cash dividends or spinoffs. Includes opening and closing cross volumes if applicable.',
    `closeadj` Float64 COMMENT 'Close Price - Adjusted for Splits Dividends and Spinoffs: The official exchange close price, adjusted for stock splits, stock dividends, cash dividends and spinoffs.',
    `closeunadj` Float64 COMMENT 'Close Price - Unadjusted: The official exchange close price, not adjusted for stock splits, stock dividends, cash dividends or spinoffs.',
    `lastupdated` DateTime('America/New_York') DEFAULT toDateTime(concat(toString(today()), ' 23:59:59'), 'America/New_York') COMMENT 'Last Updated DateTime: Automatically set to end-of-day for real-time data support.'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'End-of-day (EOD) price and volume data for publicly traded equities. Includes unadjusted, split-adjusted, and fully adjusted prices. Sourced from Sharadar SEP table.';

-- SFP: Sharadar Fund Prices Table
-- This table stores end-of-day (EOD) price and volume data specifically for listed funds (e.g., ETFs).
-- It mirrors the structure of the SEP table, providing unadjusted, split-adjusted, and fully adjusted prices for fund securities.
CREATE TABLE IF NOT EXISTS sfp
(
    `ticker` LowCardinality(String) COMMENT 'Ticker Symbol: The ticker is a unique identifier for a security in the database. Where a company is delisted and the ticker subsequently recycled for use by a different company, we utilise that ticker for the currently active company and append a number to the ticker of the delisted company. The ACTIONS table provides a record of historical ticker changes.',
    `date` Date COMMENT 'Price Date: The trade date of the price observations.',
    `open` Float64 COMMENT 'Open Price - Split Adjusted: The official exchange opening price, adjusted for stock splits and stock dividends. Not adjusted for cash dividends or spinoffs.',
    `high` Float64 COMMENT 'High Price - Split Adjusted: The high share price, adjusted for stock splits and stock dividends. Not adjusted for cash dividends or spinoffs.',
    `low` Float64 COMMENT 'Low Price - Split Adjusted: The low share price, adjusted for stock splits and stock dividends. Not adjusted for cash dividends or spinoffs.',
    `close` Float64 COMMENT 'Close Price - Split Adjusted: The official exchange close price, adjusted for stock splits and stock dividends. Not adjusted for cash dividends or spinoffs.',
    `volume` Float64 COMMENT 'Volume - Split Adjusted: The daily traded volume across all exchanges, adjusted for stock splits and stock dividends. Not adjusted for cash dividends or spinoffs. Includes opening and closing cross volumes if applicable.',
    `closeadj` Float64 COMMENT 'Close Price - Adjusted for Splits Dividends and Spinoffs: The official exchange close price, adjusted for stock splits, stock dividends, cash dividends and spinoffs.',
    `closeunadj` Float64 COMMENT 'Close Price - Unadjusted: The official exchange close price, not adjusted for stock splits, stock dividends, cash dividends or spinoffs.',
    `lastupdated` DateTime('America/New_York') DEFAULT toDateTime(concat(toString(today()), ' 23:59:59'), 'America/New_York') COMMENT 'Last Updated DateTime: Automatically set to end-of-day for real-time data support.'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'End-of-day (EOD) price and volume data for listed funds (e.g., ETFs). Mirrors the structure of the SEP table. Sourced from Sharadar SFP table.';

-- METRICS: Sharadar METRICS Table
CREATE TABLE IF NOT EXISTS metrics
(
    `ticker` LowCardinality(String) COMMENT 'Ticker Symbol: The ticker is a unique identifier for a security in the database. Where a company is delisted and the ticker subsequently recycled for use by a different company, we utilise that ticker for the currently active company and append a number to the ticker of the delisted company. The ACTIONS table provides a record of historical ticker changes.',
    `date` Date COMMENT 'Price Date: The trade date of the most recent price and volume available.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Last Updated DateTime: Timestamp when this record was updated, useful for syncing local records.',
    `beta1y` Float64 COMMENT 'Beta - 1 Year Daily: The beta of the stock over 1 year relative to the market calculated using daily adjusted closing price of the stock (as adjusted for stock splits, dividends and spinoffs) relative to total returns of the market as represented by the adjusted closing prices of the SPY S&P500 ETF. Recalculated and updated on a weekly basis.',
    `beta5y` Float64 COMMENT 'Beta - 5 Year Monthly: The beta of the stock over 5 years relative to the market calculated using monthly adjusted closing price of the stock (as adjusted for stock splits, dividends and spinoffs) relative to total returns of the market as represented by the adjusted closing prices of the SPY S&P500 ETF. Recalculated and updated on a weekly basis.',
    `dividendyieldforward` Float64 COMMENT 'Dividend Yield - Forward: The forward dividend yield, calculated by annualising the last regular cash dividend payment, dividing by the stock price and multiplying by 100.',
    `dividendyieldtrailing` Float64 COMMENT 'Dividend Yield - Trailing: The trailing dividend yield, calculated by summing regular and special cash dividend payments in the last year, dividing by the stock price and multiplying by 100.',
    `high52w` Float64 COMMENT 'High Price - 52 Week: The highest price over the last 52 weeks as adjusted for stock splits and stock dividends, but not cash dividends or spinoffs.',
    `high5y` Float64 COMMENT 'High Price - 5 Year: The highest price over the last 5 years as adjusted for stock splits and stock dividends, but not cash dividends or spinoffs.',
    `low52w` Float64 COMMENT 'Low Price - 52 Week: The lowest price over the last 52 weeks as adjusted for stock splits and stock dividends, but not cash dividends or spinoffs.',
    `low5y` Float64 COMMENT 'Low Price - 5 Year: The lowest price over the last 5 years weeks as adjusted for stock splits and stock dividends, but not cash dividends or spinoffs.',
    `ma200d` Float64 COMMENT 'Price Moving Average - 200 Day: The 200 day moving average closing price as adjusted for stock splits and stock dividends, but not cash dividends or spinoffs. Not available if the stock has been trading less than 200 days.',
    `ma200w` Float64 COMMENT 'Price Moving Average - 200 Week: The 200 week moving average closing price as adjusted for stock splits and stock dividends, but not cash dividends or spinoffs. Not available if the stock has been trading less than 200 weeks.',
    `ma50d` Float64 COMMENT 'Price Moving Average - 50 Day: The 50 day moving average closing price as adjusted for stock splits and stock dividends, but not cash dividends or spinoffs. Not available if the stock has been trading less than 50 days.',
    `ma50w` Float64 COMMENT 'Price Moving Average - 50 Week: The 50 week moving average closing price as adjusted for stock splits and stock dividends, but not cash dividends or spinoffs. Not available if the stock has been trading less than 50 weeks.',
    `price` Float64 COMMENT 'Price: The closing stock price on the date.',
    `return1y` Float64 COMMENT 'Total Return - 1 Year: The total return over 1 year calculated using the closing price as adjusted for stock splits and stock dividends, but not cash dividends or spinoffs. Not available if the stock has been trading for less than 1 year.',
    `return5y` Float64 COMMENT 'Total Return - 5 Year: The total return over 5 years calculated using the closing price as adjusted for stock splits and stock dividends, but not cash dividends or spinoffs. Not available if the stock has been trading for less than 5 years.',
    `returnytd` Float64 COMMENT 'Total Return - Year to Date: The total return for the year to date calculated using the closing price as adjusted for stock splits and stock dividends, but not cash dividends or spinoffs.',
    `volume` Float64 COMMENT 'Volume: The daily traded volume across all exchanges, adjusted for stock splits and stock dividends. Not adjusted for cash dividends or spinoffs. Includes opening and closing cross volumes if applicable.',
    `volumeavg1m` Float64 COMMENT 'Volume Average - 1 Month: The daily average traded volume over 1 month across all exchanges, adjusted for stock splits and stock dividends. Not adjusted for cash dividends or spinoffs. Includes opening and closing cross volumes if applicable.',
    `volumeavg3m` Float64 COMMENT 'Volume Average - 3 Month: The daily average traded volume over 3 months across all exchanges, adjusted for stock splits and stock dividends. Not adjusted for cash dividends or spinoffs. Includes opening and closing cross volumes if applicable.'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'Various daily-refreshed metrics from Sharadar, like beta, dividend yields, and 52-week highs/lows. Distinct from project-calculated derived metrics. Sourced from Sharadar METRICS table.';

-- DAILY: Sharadar Daily Fundamental Metrics Table
-- This table provides key valuation and fundamental metrics calculated on a daily basis, using the most recent financial data combined with daily market prices.
-- It includes metrics like Enterprise Value (EV), Market Cap, P/E, P/B, and P/S ratios, offering a timely view of company valuations.
CREATE TABLE IF NOT EXISTS daily
(
    `ticker` LowCardinality(String) COMMENT 'Ticker Symbol: The ticker is a unique identifier for a security in the database. Where a company is delisted and the ticker subsequently recycled for use by a different company, we utilise that ticker for the currently active company and append a number to the ticker of the delisted company. The ACTIONS table provides a record of historical ticker changes.',
    `date` Date COMMENT 'Price Date: The trade date of the price observations used in determining [MarketCap], [PE], [PS] etc.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Last Updated DateTime: Timestamp when this record was updated, useful for syncing local records.',
    `ev` Float64 COMMENT 'Enterprise Value - Daily: Enterprise value is a measure of the value of a business as a whole, calculated as [MarketCap] plus [DebtUSD] minus [CashnEqUSD]. [MarketCap] is calculated by us, and the remaining figures are sourced from the most recent SEC form 10 filings.',
    `evebit` Float64 COMMENT 'Enterprise Value over EBIT - Daily: Measures the ratio between [EV] and [EBITUSD]. EBITUSD is derived from the most recent SEC form 10 filings.',
    `evebitda` Float64 COMMENT 'Enterprise Value over EBITDA - Daily: Measures the ratio between [EV] and [EBITDAUSD]. EBITDAUSD is derived from the most recent SEC form 10 filings.',
    `marketcap` Float64 COMMENT 'Market Capitalization - Daily (millions USD): Sharadar stores this as millions of nominal USD. Definition: product of [SharesBas], [Price] and [ShareFactor]; [SharesBas] from the most recent SEC form 10 filing.',
    `pb` Float64 COMMENT 'Price to Book Value - Daily: Measures the ratio between [MarketCap] and [EquityUSD]. [EquityUSD] is sourced from the most recent SEC form 10 filing.',
    `pe` Float64 COMMENT 'Price Earnings (Damodaran Method) - Daily: Measures the ratio between [MarketCap] and [NetIncCmnUSD]. [NetIncCmnUSD] is sourced from the most recent SEC form 10 filings.',
    `ps` Float64 COMMENT 'Price Sales (Damodaran Method) - Daily: Measures the ratio between [MarketCap] and [RevenueUSD]. [RevenueUSD] is sourced from the most recent SEC form 10 filings.'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'Key valuation and fundamental metrics calculated by Sharadar on a daily basis (EV, Market Cap, P/E, P/B, P/S). Sourced from Sharadar DAILY table.';

-- SF1: Sharadar Core US Fundamentals Table
-- This table is the primary repository for US company fundamental data, sourced from SEC filings.
-- It contains detailed financial statements (Income Statement, Balance Sheet, Cash Flow) and a wide array of derived financial metrics and ratios.
-- Data is provided across multiple reporting dimensions (e.g., ARQ/MRQ for quarterly, ARY/MRY for annual, ART/MRT for TTM) to reflect different filing statuses (as reported, restated) and periods.
CREATE TABLE IF NOT EXISTS sf1
(
    `ticker` LowCardinality(String) COMMENT 'Ticker Symbol: [Entity] The ticker is a unique identifier for a security in the database. Where a company is delisted and the ticker subsequently recycled for use by a different company, we utilise that ticker for the currently active company and append a number to the ticker of the delisted company. The ACTIONS table provides a record of historical ticker changes.',
    `dimension` LowCardinality(String) COMMENT 'Dimension: [Entity] The dimension field allows you to take different dimensional views of data over time. ARQ: Quarterly, excluding restatements, MRQ: Quarterly, including restatements, ARY: annual, excluding restatements, MRY: annual, including restatements, ART: trailing-twelve-months, excluding restatements, MRT: trailing-twelve-months, including restatements.',
    `calendardate` Date COMMENT 'Calendar Date: [Entity] The Calendar Date represents the normalized [ReportPeriod]. This provides a common date to query for which is necessary due to irregularity in report periods across companies. For example, if the report period is 2015-09-26, the calendar date will be 2015-09-30 for quarterly and trailing-twelve-month dimensions (ARQ,MRQ,ART,MRT), and 2015-12-31 for annual dimensions (ARY,MRY). We also employ offsets in order to maximise comparability of the period across companies. For example consider two companies: one with a quarter ending on 2018-07-24, and the other with a quarter ending on 2018-06-28. A naive normalization process would assign these to differing calendar quarters of 2018-09-30 and 2018-06-30 respectively. However, we assign these both to the 2018-06-30 calendar quarter because this maximises the overlap in the report periods in question and therefore the comparability of this period.',
    `date` Date COMMENT 'Date: [Entity] SEC filing date for AR dimensions (ARQ,ART,ARY), and [REPORTPERIOD] for MR dimensions (MRQ,MRT,MRY). Observation date for price-based fields (MarketCap, PE). Retail Sharadar name (formerly datekey).',
    `reportperiod` Date COMMENT 'Report Period: [Entity] The Report Period represents the end date of the fiscal period.',
    `fiscalperiod` LowCardinality(String) COMMENT 'Fiscal Period: The fiscal period of the report expressed as follows: 2024-Q2, 2024-Q3, 2024-FY etc. Note that companies can have different fiscal periods for the report period due to different year end dates.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Last Updated DateTime: Timestamp when this record was updated, useful for syncing local records.',
    `accoci` Float64 COMMENT 'Accumulated Other Comprehensive Income: [Balance Sheet] A component of [Equity] representing the accumulated change in equity from transactions and other events and circumstances from non-owner sources, net of tax effect, at period end. Includes foreign currency translation items, certain pension adjustments, unrealized gains and losses on certain investments in debt and equity securities. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `assets` Float64 COMMENT 'Total Assets: [Balance Sheet] Sum of the carrying amounts as of the balance sheet date of all assets that are recognized. Major components are [CashnEq], [Investments],[Intangibles], [PPNENet],[TaxAssets] and [Receivables].',
    `assetsavg` Float64 COMMENT 'Average Assets: [Metrics] Average asset value for the period used in calculation of [ROE] and [ROA], derived from [Assets].',
    `assetsc` Float64 COMMENT 'Current Assets: [Balance Sheet] The current portion of [Assets], reported if a company operates a classified balance sheet that segments current and non-current assets.',
    `assetsnc` Float64 COMMENT 'Assets Non-Current: [Balance Sheet] Amount of non-current assets, for companies that operate a classified balance sheet. Calculated as the different between Total Assets [Assets] and Current Assets [AssetsC].',
    `assetturnover` Float64 COMMENT 'Asset Turnover: [Metrics] Asset turnover is a measure of a firms operating efficiency, calculated by dividing [Revenue] by [AssetsAVG]. Often a component of DuPont ROE analysis.',
    `bvps` Float64 COMMENT 'Book Value per Share: [Metrics] Measures the ratio between [Equity] and [SharesWA] as adjusted by [ShareFactor].',
    `capex` Float64 COMMENT 'Capital Expenditure: [Cash Flow Statement] A component of [NCFI] representing the net cash inflow (outflow) associated with the acquisition & disposal of long-lived, physical & intangible assets that are used in the normal conduct of business to produce goods and services and are not intended for resale. Includes cash inflows/outflows to pay for construction of self-constructed assets & software. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `cashneq` Float64 COMMENT 'Cash and Equivalents: [Balance Sheet] A component of [Assets] representing the amount of currency on hand as well as demand deposits with banks or financial institutions. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `cashnequsd` Float64 COMMENT 'Cash and Equivalents (USD): [Balance Sheet] [CashnEq] in USD, converted by [FXUSD]. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `cor` Float64 COMMENT 'Cost of Revenue: [Income Statement] The aggregate cost of goods produced and sold and services rendered during the reporting period. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `consolinc` Float64 COMMENT 'Consolidated Income: [Income Statement] The portion of profit or loss for the period, net of income taxes, which is attributable to the consolidated entity, before the deduction of [NetIncNCI].',
    `currentratio` Float64 COMMENT 'Current Ratio: [Metrics] The ratio between [AssetsC] and [LiabilitiesC], for companies that operate a classified balance sheet.',
    `de` Float64 COMMENT 'Debt to Equity Ratio: [Metrics] Measures the ratio between [Liabilities] and [Equity].',
    `debt` Float64 COMMENT 'Total Debt: [Balance Sheet] A component of [Liabilities] representing the total amount of current and non-current debt owed. Includes secured and unsecured bonds issued, commercial paper, notes payable, credit facilities, lines of credit, capital lease obligations, operating lease obligations, and convertible notes. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `debtc` Float64 COMMENT 'Debt Current: [Balance Sheet] The current portion of [Debt], reported if the company operates a classified balance sheet that segments current and non-current liabilities. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `debtnc` Float64 COMMENT 'Debt Non-Current: [Balance Sheet] The non-current portion of [Debt] reported if the company operates a classified balance sheet that segments current and non-current liabilities. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `debtusd` Nullable(Float64) COMMENT 'Total Debt (USD): [Balance Sheet] [Debt] in USD, converted by [FXUSD]. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `deferredrev` Float64 COMMENT 'Deferred Revenue: [Balance Sheet] A component of [Liabilities] representing the carrying amount of consideration received or receivable on potential earnings that were not recognized as revenue, including sales, license fees, and royalties, but excluding interest income. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `depamor` Float64 COMMENT 'Depreciation Amortization & Accretion: [Cash Flow Statement] A component of operating cash flow representing the aggregate net amount of depreciation, amortization, and accretion recognized during an accounting period. As a non-cash item, the net amount is added back to net income when calculating cash provided by or used in operations using the indirect method. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `deposits` Float64 COMMENT 'Deposit Liabilities: [Balance Sheet] A component of [Liabilities] representing the total of all deposit liabilities held, including foreign and domestic, interest and noninterest bearing. May include demand deposits, saving deposits, Negotiable Order of Withdrawal and time deposits among others. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `divyield` Float64 COMMENT 'Dividend Yield: [Metrics] Dividend Yield measures the ratio between a company\'s [DPS] and its [Price]. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `dps` Float64 COMMENT 'Dividends per Basic Common Share: [Income Statement] Aggregate dividends declared during the period for each split-adjusted share of common stock outstanding. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `ebit` Float64 COMMENT 'Earning Before Interest & Taxes (EBIT): [Income Statement] Earnings Before Interest and Tax is calculated by adding [TaxExp] and [IntExp] back to [NetInc].',
    `ebitda` Float64 COMMENT 'Earnings Before Interest Taxes & Depreciation Amortization (EBITDA): [Metrics] EBITDA is a non-GAAP accounting metric that is widely used when assessing the performance of companies, calculated by adding [DepAmor] back to [EBIT].',
    `ebitdamargin` Float64 COMMENT 'EBITDA Margin: [Metrics] Measures the ratio between a company\'s [EBITDA] and [Revenue].',
    `ebitdausd` Nullable(Float64) COMMENT 'Earnings Before Interest Taxes & Depreciation Amortization (USD): [Metrics] [EBITDA] in USD, converted by [FXUSD].',
    `ebitusd` Nullable(Float64) COMMENT 'Earning Before Interest & Taxes (USD): [Income Statement] [EBIT] in USD, converted by [FXUSD].',
    `ebt` Float64 COMMENT 'Earnings before Tax: [Metrics] Earnings Before Tax is calculated by adding [TaxExp] back to [NetInc].',
    `eps` Float64 COMMENT 'Earnings per Basic Share: [Income Statement] Earnings per share as calculated and reported by the company. Approximates to the amount of [NetIncCmn] for the period per each [SharesWA] after adjusting for [ShareFactor].',
    `epsdil` Float64 COMMENT 'Earnings per Diluted Share: [Income Statement] Earnings per diluted share as calculated and reported by the company. Approximates to the amount of [NetIncCmn] for the period per each [SharesWADil] after adjusting for [ShareFactor]..',
    `epsusd` Float64 COMMENT 'Earnings per Basic Share (USD): [Income Statement] [EPS] in USD, converted by [FXUSD].',
    `equity` Float64 COMMENT 'Shareholders Equity Attributable to Parent: [Balance Sheet] A principal component of the balance sheet, in addition to [Liabilities] and [Assets], that represents the total of all stockholders\' equity (deficit) items, net of receivables from officers, directors, owners, and affiliates of the entity which are attributable to the parent.',
    `equityavg` Float64 COMMENT 'Average Equity: [Metrics] Average equity value for the period used in calculation of [ROE], derived from [Equity].',
    `equityusd` Nullable(Float64) COMMENT 'Shareholders Equity (USD): [Balance Sheet] [Equity] in USD, converted by [FXUSD].',
    `ev` Nullable(Float64) COMMENT 'Enterprise Value: [Metrics] Enterprise value is a measure of the value of a business as a whole, calculated as [MarketCap] plus [DebtUSD] minus [CashnEqUSD].',
    `evebit` Float64 COMMENT 'Enterprise Value over EBIT: [Metrics] Measures the ratio between [EV] and [EBITUSD].',
    `evebitda` Float64 COMMENT 'Enterprise Value over EBITDA: [Metrics] Measures the ratio between [EV] and [EBITDAUSD].',
    `fcf` Float64 COMMENT 'Free Cash Flow: [Metrics] Free Cash Flow is a measure of financial performance calculated as [NCFO] minus [CapEx].',
    `fcfps` Float64 COMMENT 'Free Cash Flow per Share: [Metrics] Free Cash Flow per Share is a valuation metric calculated by dividing [FCF] by [SharesWA] and [ShareFactor].',
    `fxusd` Float64 COMMENT 'Foreign Currency to USD Exchange Rate: [Metrics] The exchange rate used for the conversion of foreign currency to USD for non-US companies that do not report in USD.',
    `gp` Float64 COMMENT 'Gross Profit: [Income Statement] Aggregate revenue [Revenue] less cost of revenue [CoR] directly attributable to the revenue generation activity.',
    `grossmargin` Float64 COMMENT 'Gross Margin: [Metrics] Gross Margin measures the ratio between a company\'s [GP] and [Revenue].',
    `intangibles` Float64 COMMENT 'Goodwill and Intangible Assets: [Balance Sheet] A component of [Assets] representing the carrying amounts of all intangible assets and goodwill as of the balance sheet date, net of accumulated amortization and impairment charges. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `intexp` Float64 COMMENT 'Interest Expense: [Income Statement] Amount of the cost of borrowed funds accounted for as interest expense. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `invcap` Float64 COMMENT 'Invested Capital: [Metrics] Invested capital is an input into the calculation of [ROIC], and is calculated as: [Debt] plus [Assets] minus [Intangibles] minus [CashnEq] minus [LiabilitiesC]. Please note this calculation method is subject to change.',
    `invcapavg` Float64 COMMENT 'Invested Capital Average: [Metrics] Average invested capital value for the period used in the calculation of [ROIC], and derived from [InvCap]. Invested capital is an input into the calculation of [ROIC], and is calculated as: [Debt] plus [Assets] minus [Intangibles] minus [CashnEq] minus [LiabilitiesC]. Please note this calculation method is subject to change.',
    `inventory` Float64 COMMENT 'Inventory: [Balance Sheet] A component of [Assets] representing the amount after valuation and reserves of inventory expected to be sold, or consumed within one year or operating cycle, if longer. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `investments` Float64 COMMENT 'Investments: [Balance Sheet] A component of [Assets] representing the total amount of marketable and non-marketable securties, loans receivable and other invested assets. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `investmentsc` Float64 COMMENT 'Investments Current: [Balance Sheet] The current portion of [Investments], reported if the company operates a classified balance sheet that segments current and non-current assets. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `investmentsnc` Float64 COMMENT 'Investments Non-Current: [Balance Sheet] The non-current portion of [Investments], reported if the company operates a classified balance sheet that segments current and non-current assets. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `liabilities` Float64 COMMENT 'Total Liabilities: [Balance Sheet] Sum of the carrying amounts as of the balance sheet date of all liabilities that are recognized. Principal components are [Debt], [DeferredRev], [Payables],[Deposits], and [TaxLiabilities].',
    `liabilitiesc` Float64 COMMENT 'Current Liabilities: [Balance Sheet] The current portion of [Liabilities], reported if the company operates a classified balance sheet that segments current and non-current liabilities.',
    `liabilitiesnc` Float64 COMMENT 'Liabilities Non-Current: [Balance Sheet] The non-current portion of [Liabilities], reported if the company operates a classified balance sheet that segments current and non-current liabilities.',
    `marketcap` Nullable(Float64) COMMENT 'Market Capitalization: [Metrics] Represents the product of [SharesBas], [Price] and [ShareFactor].',
    `ncf` Float64 COMMENT 'Net Cash Flow / Change in Cash & Cash Equivalents: [Cash Flow Statement] Principal component of the cash flow statement representing the amount of increase (decrease) in cash and cash equivalents. Includes [NCFO], investing [NCFI] and financing [NCFF] for continuing and discontinued operations, and the effect of exchange rate changes on cash [NCFX].',
    `ncfbus` Float64 COMMENT 'Net Cash Flow - Business Acquisitions and Disposals: [Cash Flow Statement] A component of [NCFI] representing the net cash inflow (outflow) associated with the acquisition & disposal of businesses, joint-ventures, affiliates, and other named investments. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `ncfcommon` Float64 COMMENT 'Issuance (Purchase) of Equity Shares: [Cash Flow Statement] A component of [NCFF] representing the net cash inflow (outflow) from common equity changes. Includes additional capital contributions from share issuances and exercise of stock options, and outflow from share repurchases.  Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `ncfdebt` Float64 COMMENT 'Issuance (Repayment) of Debt Securities : [Cash Flow Statement] A component of [NCFF] representing the net cash inflow (outflow) from issuance (repayment) of debt securities. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `ncfdiv` Float64 COMMENT 'Payment of Dividends & Other Cash Distributions   : [Cash Flow Statement] A component of [NCFF] representing dividends and dividend equivalents paid on common stock and restricted stock units. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `ncff` Float64 COMMENT 'Net Cash Flow from Financing: [Cash Flow Statement] A component of [NCF] representing the amount of cash inflow (outflow) from financing activities, from continuing and discontinued operations. Principal components of financing cash flow are: issuance (purchase) of equity shares, issuance (repayment) of debt securities, and payment of dividends & other cash distributions. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `ncfi` Float64 COMMENT 'Net Cash Flow from Investing: [Cash Flow Statement] A component of [NCF] representing the amount of cash inflow (outflow) from investing activities, from continuing and discontinued operations. Principal components of investing cash flow are: capital (expenditure) disposal of equipment [CapEx], business (acquisitions) disposition [NCFBus] and investment (acquisition) disposal [NCFInv]. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `ncfinv` Float64 COMMENT 'Net Cash Flow - Investment Acquisitions and Disposals: [Cash Flow Statement] A component of [NCFI] representing the net cash inflow (outflow) associated with the acquisition & disposal of investments, including marketable securities and loan originations. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `ncfo` Float64 COMMENT 'Net Cash Flow from Operations: [Cash Flow Statement] A component of [NCF] representing the amount of cash inflow (outflow) from operating activities, from continuing and discontinued operations.',
    `ncfx` Float64 COMMENT 'Effect of Exchange Rate Changes on Cash : [Cash Flow Statement] A component of Net Cash Flow [NCF] representing the amount of increase (decrease) from the effect of exchange rate changes on cash and cash equivalent balances held in foreign currencies. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `netinc` Float64 COMMENT 'Net Income: [Income Statement] The portion of profit or loss for the period, net of income taxes, which is attributable to the parent after the deduction of [NetIncNCI] from [ConsolInc], and before the deduction of [PrefDivIS].',
    `netinccmn` Float64 COMMENT 'Net Income Common Stock: [Income Statement] The amount of net income (loss) for the period due to common shareholders. Typically differs from [NetInc] to the parent entity due to the deduction of [PrefDivIS].',
    `netinccmnusd` Nullable(Float64) COMMENT 'Net Income Common Stock (USD): [Income Statement] [NetIncCmn] in USD, converted by [FXUSD].',
    `netincdis` Float64 COMMENT 'Net Loss Income from Discontinued Operations: [Income Statement] Amount of loss (income) from a disposal group, net of income tax, reported as a separate component of income. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `netincnci` Float64 COMMENT 'Net Income to Non-Controlling Interests: [Income Statement] The portion of income which is attributable to non-controlling interest shareholders, subtracted from [ConsolInc] in order to obtain [NetInc]. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `netmargin` Float64 COMMENT 'Profit Margin: [Metrics] Measures the ratio between a company\'s [NetIncCmn] and [Revenue].',
    `opex` Float64 COMMENT 'Operating Expenses: [Income Statement] Operating expenses represent the total expenditure on [SGnA], [RnD] and other operating expense items, it excludes [CoR].',
    `opinc` Float64 COMMENT 'Operating Income: [Income Statement] Operating income is a measure of financial performance before the deduction of [IntExp], [TaxExp] and other Non-Operating items. It is calculated as [GP] minus [OpEx].',
    `payables` Float64 COMMENT 'Trade and Non-Trade Payables: [Balance Sheet] A component of [Liabilities] representing trade and non-trade payables. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `payoutratio` Float64 COMMENT 'Payout Ratio: [Metrics] The percentage of earnings paid as dividends to common stockholders. Calculated by dividing [DPS] by [EPSUSD].',
    `pb` Float64 COMMENT 'Price to Book Value: [Metrics] Measures the ratio between [MarketCap] and [EquityUSD].',
    `pe` Float64 COMMENT 'Price Earnings (Damodaran Method): [Metrics] Measures the ratio between [MarketCap] and [NetIncCmnUSD]',
    `pe1` Float64 COMMENT 'Price to Earnings Ratio: [Metrics] An alternative to [PE] representing the ratio between [Price] and [EPSUSD].',
    `ppnenet` Float64 COMMENT 'Property Plant & Equipment Net: [Balance Sheet] A component of [Assets] representing the amount after accumulated depreciation, depletion and amortization of physical assets used in the normal conduct of business to produce goods and services and not intended for resale. Includes Operating Right of Use Assets. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `prefdivis` Float64 COMMENT 'Preferred Dividends Income Statement Impact: [Income Statement] Income statement item reflecting dividend payments to preferred stockholders. Subtracted from Net Income to Parent [NetInc] to obtain Net Income to Common Stockholders [NetIncCmn]. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `price` Float64 COMMENT 'Share Price (Adjusted Close): [Entity] The price per common share adjusted for stock splits but not adjusted for dividends, used in the computation of [PE1], [PS1], [DivYield] and [SPS].',
    `ps` Float64 COMMENT 'Price Sales (Damodaran Method): [Metrics] Measures the ratio between [MarketCap] and [RevenueUSD].',
    `ps1` Float64 COMMENT 'Price to Sales Ratio: [Metrics] An alternative calculation method to [PS], that measures the ratio between a company\'s [Price] and it\'s [SPS].',
    `receivables` Float64 COMMENT 'Trade and Non-Trade Receivables: [Balance Sheet] A component of [Assets] representing trade and non-trade receivables. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `retearn` Float64 COMMENT 'Accumulated Retained Earnings (Deficit): [Balance Sheet] A component of [Equity] representing the cumulative amount of the entities undistributed earnings or deficit. May only be reported annually by certain companies, rather than quarterly.',
    `revenue` Float64 COMMENT 'Revenues: [Income Statement] The amount of Revenue recognised from goods sold, services rendered, insurance premiums, or other activities that constitute an earning process. Interest income for financial institutions is reported net of interest expense and provision for credit losses. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `revenueusd` Nullable(Float64) COMMENT 'Revenues (USD): [Income Statement] [Revenue] in USD, converted by [FXUSD]. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `rnd` Float64 COMMENT 'Research and Development Expense: [Income Statement] A component of [OpEx] representing the aggregate costs incurred in a planned search or critical investigation aimed at discovery of new knowledge with the hope that such knowledge will be useful in developing a new product or service. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `roa` Float64 COMMENT 'Return on Average Assets: [Metrics] Return on assets measures how profitable a company is [NetIncCmn] relative to its total assets [AssetsAvg].',
    `roe` Float64 COMMENT 'Return on Average Equity: [Metrics] Return on equity measures a corporation\'s profitability by calculating the amount of [NetIncCmn] returned as a percentage of [EquityAvg].',
    `roic` Float64 COMMENT 'Return on Invested Capital: [Metrics] Return on Invested Capital is a ratio estimated by dividing [EBIT] by [InvCapAvg]. [InvCap] is calculated as: [Debt] plus [Assets] minus [Intangibles] minus [CashnEq] minus [LiabilitiesC]. Please note this calculation method is subject to change.',
    `ros` Float64 COMMENT 'Return on Sales: [Metrics] Return on Sales is a ratio to evaluate a company\'s operational efficiency, calculated by dividing [EBIT] by [Revenue]. ROS is often a component of DuPont ROE analysis.',
    `sbcomp` Float64 COMMENT 'Share Based Compensation: [Cash Flow Statement] A component of [NCFO] representing the total amount of noncash, equity-based employee remuneration. This may include the value of stock or unit options, amortization of restricted stock or units, and adjustment for officers\' compensation. As noncash, this element is an add back when calculating net cash generated by operating activities using the indirect method.',
    `sgna` Float64 COMMENT 'Selling General and Administrative Expense: [Income Statement] A component of [OpEx] representing the aggregate total costs related to selling a firm\'s product and services, as well as all other general and administrative expenses. Direct selling expenses (for example, credit, warranty, and advertising) are expenses that can be directly linked to the sale of specific products. Indirect selling expenses are expenses that cannot be directly linked to the sale of specific products, for example telephone expenses, Internet, and postal charges. General and administrative expenses include salaries of non-sales personnel, rent, utilities, communication, etc. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `sharefactor` Float64 COMMENT 'Share Factor: [Entity] Share factor is a multiplicand in the calculation of [MarketCap] and is used to adjust for: American Depository Receipts (ADRs) that represent more or less than 1 underlying share, and, companies which have different earnings share for different share classes (eg Berkshire Hathaway - BRK.B).',
    `sharesbas` Float64 COMMENT 'Shares (Basic): [Entity] The number of shares or other units outstanding of the entity\'s capital or common stock or other ownership interests, as stated on the cover of related periodic report (10-K/10-Q), after adjustment for stock splits.',
    `shareswa` Float64 COMMENT 'Weighted Average Shares: [Income Statement] The weighted average number of shares or units issued and outstanding that are used by the company to calculate [EPS], determined based on the timing of issuance of shares or units in the period.',
    `shareswadil` Float64 COMMENT 'Weighted Average Shares Diluted: [Income Statement] The weighted average number of shares or units issued and outstanding that are used by the company to calculate [EPSDil], determined based on the timing of issuance of shares or units in the period.',
    `sps` Float64 COMMENT 'Sales per Share: [Metrics] Sales per Share measures the ratio between [RevenueUSD] and [SharesWA] as adjusted by [ShareFactor].',
    `tangibles` Float64 COMMENT 'Tangible Asset Value: [Metrics] The value of tangibles assets calculated as the difference between [Assets] and [Intangibles].',
    `taxassets` Float64 COMMENT 'Tax Assets: [Balance Sheet] A component of [Assets] representing tax assets and receivables. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `taxexp` Float64 COMMENT 'Income Tax Expense: [Income Statement] Amount of current income tax expense (benefit) and deferred income tax expense (benefit) pertaining to continuing operations. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `taxliabilities` Float64 COMMENT 'Tax Liabilities: [Balance Sheet] A component of [Liabilities] representing outstanding tax liabilities. Where this item is not contained on the company consolidated financial statements and cannot otherwise be imputed the value of 0 is used.',
    `tbvps` Float64 COMMENT 'Tangible Assets Book Value per Share: [Metrics] Measures the ratio between [Tangibles] and [SharesWA] as adjusted by [ShareFactor].',
    `workingcapital` Float64 COMMENT 'Working Capital: [Metrics] Working capital measures the difference between [AssetsC] and [LiabilitiesC].'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(calendardate)
ORDER BY (ticker, date, dimension, reportperiod)
SETTINGS index_granularity = 8192
COMMENT 'Primary US company fundamental data from SEC filings. Contains detailed financial statements and ratios across multiple dimensions (ARQ, ARY, TTM). Sourced from Sharadar SF1 / fundamentals table.';

-- ACTIONS: Sharadar Corporate Actions Table
-- This table records significant corporate actions affecting securities, such as cash dividends, stock splits, mergers, acquisitions, ticker changes, and delistings.
-- It provides historical context crucial for accurately interpreting price and fundamental data.
CREATE TABLE IF NOT EXISTS actions
(
    `date` Date COMMENT 'Date: The date of the corporate action.',
    `action` LowCardinality(String) COMMENT 'Action: Action code as defined by Sharadar action-reference metadata.',
    `ticker` LowCardinality(String) COMMENT 'Ticker Symbol: The ticker is a unique identifier for a security in the database. Where a company is delisted and the ticker subsequently recycled for use by a different company, we utilise that ticker for the currently active company and append a number to the ticker of the delisted company. The ACTIONS table provides a record of historical ticker changes.',
    `name` String COMMENT 'Issuer Name: The name of the issuer.',
    `value` Nullable(Float64) COMMENT 'Value: Associated value; interpretation depends on the action code.',
    `contraticker` String COMMENT 'Contra Ticker Symbol: The contra ticker associated with the action, if applicable.',
    `contraname` String COMMENT 'Contra Issuer Name: The name of the contra issuer associated with the contra ticker.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Last Updated DateTime: Synthetic timestamp for deduplication in ReplacingMergeTree. Set to current time during data load.'
)
ENGINE = ReplacingMergeTree(lastupdated)
ORDER BY (date, ticker, action, contraticker, contraname, name)
SETTINGS index_granularity = 8192
COMMENT 'Records significant corporate actions (dividends, splits, mergers, ticker changes) affecting securities. Provides crucial historical context. Sourced from Sharadar ACTIONS table.';

-- EVENTS: Sharadar Material Corporate Events Table
-- This table captures material corporate events as disclosed in SEC Form 8-K filings.
-- It includes the filing date, ticker, and event codes that categorize the nature of the reported events.
CREATE TABLE IF NOT EXISTS events
(
    `ticker` LowCardinality(String) COMMENT 'Ticker Symbol: The ticker is a unique identifier for a security in the database. Where a company is delisted and the ticker subsequently recycled for use by a different company, we utilise that ticker for the currently active company and append a number to the ticker of the delisted company. The ACTIONS table provides a record of historical ticker changes.',
    `date` Date COMMENT 'Filing Date: The date of the form 8 SEC filing.',
    `eventcodes` String COMMENT 'Material Corporate Events: Each type of event is assigned a 2-digit numeric code defined by Sharadar event-code reference metadata.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'Captures material corporate events as disclosed in SEC Form 8-K filings. Sourced from Sharadar EVENTS table.';

-- SF2: Sharadar Core US Insiders Table
-- This table tracks insider trading activity, detailing transactions and holdings by corporate insiders (officers, directors, significant shareholders).
-- Data is sourced from SEC Forms 3, 4, and 5, providing insights into insider sentiment and potential future stock performance.
CREATE TABLE IF NOT EXISTS sf2
(
    `ticker` LowCardinality(String) COMMENT 'Ticker Symbol: The ticker is a unique identifier for a security in the database. Where a company is delisted and the ticker subsequently recycled for use by a different company, we utilise that ticker for the currently active company and append a number to the ticker of the delisted company. The ACTIONS table provides a record of historical ticker changes.',
    `date` Date COMMENT 'Filing Date: The date the form was filed with the SEC (retail insiders table).',
    `formtype` String COMMENT 'Form Type: The type of SEC form . Available options are 3, 4 or 5 that the data are sourced from. Preprended by RESTATED in the event that the filing is subsequently restated.',
    `ownername` String COMMENT 'Owner Name (Insider / Investor): The name of the owner.',
    `officertitle` String COMMENT 'Officer Title: Is the owner is an officer of the company the officer\'s title is provided.',
    `isdirector` String COMMENT 'Is Director?: Is the owner a Board Director? [Y]es or [N]o.',
    `isofficer` String COMMENT 'Is Officer?: Is the owner an officer of the company? [Y]es or [N]o.',
    `istenpercentowner` String COMMENT 'Is Ten Percent Owner?: Does the owner hold ten percent or more of the class of security? [Y]es or [N]o.',
    `transactiondate` Date COMMENT 'Transaction Date: If there has been a transaction, the date of the transaction is provided here.',
    `securityadcode` String COMMENT 'Security Acquired/Disposed Code: [D] Derivative, No Transaction [DA] Derivative Acquisition [DD] Derivative Disposition [N] Non-Derivative, No Transaction [NA] Non-Derivative Acquisition [ND] Non-Derivative Disposition',
    `transactioncode` String COMMENT 'Transaction Code: The available [Transaction Codes] [Transaction Categories] Descriptions are as follows: [P] [General] Open market or private purchase of non-derivative or derivative security [S] [General] Open market or private sale of non-derivative or derivative security [V] [General] Transaction voluntarily reported earlier than required [A] [Rule 16b-3] Grant, award or other acquisition pursuant to Rule 16b-3(d) [D] [Rule 16b-3] Disposition to the issuer of issuer equity securities pursuant to Rule 16b-3(e) [F] [Rule 16b-3] Payment of exercise price or tax liability by delivering or withholding securities [I] [Rule 16b-3] Discretionary transaction in accordance with Rule 16b-3(f) [M] [Rule 16b-3] Exercise or conversion of derivative security exempted pursuant to Rule 16b-3 [C] [Derivative Codes] Conversion of derivative security [E] [Derivative Codes] Expiration of short derivative position [H] [Derivative Codes] Expiration (or cancellation) of long derivative position with value received [O] [Derivative Codes] Exercise of out-of-the-money derivative security [X] [Derivative Codes] Exercise of in-the-money or at-the-money derivative security [G] [Other Section 16(b) Exempt] Bona fide gift [L] [Other Section 16(b) Exempt] Small acquisition under Rule 16a-6 [W] [Other Section 16(b) Exempt] Acquisition or disposition by will or the laws of descent and distribution [Z] [Other Section 16(b) Exempt] Deposit into or withdrawal from voting trust [J] [Other] Other acquisition or disposition [K] [Other] Transaction in equity swap or instrument with similar characteristics [U] [Other] Disposition pursuant to a tender of shares in a change of control transaction',
    `sharesownedbeforetransaction` Float64 COMMENT 'Shares Owned Before Transaction: The number of shares owned before the transaction.',
    `transactionshares` Float64 COMMENT 'Transaction Shares: The number of shares transacted.',
    `sharesownedfollowingtransaction` Float64 COMMENT 'Shares Owned Following Transaction: The number of shares owned following the transaction.',
    `transactionpricepershare` Float64 COMMENT 'Transaction Price per Share: The transaction price per share.',
    `transactionvalue` Nullable(Float64) COMMENT 'Transaction Value: The value of the transaction.',
    `securitytitle` String COMMENT 'Security Title: The title of the class of security.',
    `directorindirect` String COMMENT 'Direct or Indirect?: Is the ownership held [D]irectly or [I]ndirectly?',
    `natureofownership` String COMMENT 'Nature of Ownership: Where the ownership is held through an investment vehicle (trust, fund etc) the name of that investment vehicle is provided here.',
    `dateexercisable` Date COMMENT 'Date Exercisable: The date that an option is exercisable, where applicable and available.',
    `priceexercisable` Nullable(Float64) COMMENT 'Price Exercisable: The price at which an option is exercisable, where applicable and available.',
    `expirationdate` Date COMMENT 'Expiration Date: The data at which an option expires, where applicable and available',
    `rownum` Float64 COMMENT 'Row Number: The record number for a particular owner and filing date, which forms part of the key for the record.'
)
ENGINE = ReplacingMergeTree
ORDER BY (ticker, date, ownername, formtype, rownum)
SETTINGS index_granularity = 8192
COMMENT 'Tracks insider trading activity from SEC Forms 3, 4, and 5. Sourced from Sharadar SF2 / insiders table.';

-- SF3: Sharadar US Institutional Investors Table
-- This table provides data on institutional investor holdings, sourced from quarterly SEC Form 13F filings.
-- It details the securities held by large investment managers, including the value and number of units for each holding.
CREATE TABLE IF NOT EXISTS sf3
(
    `ticker` LowCardinality(String) COMMENT 'Ticker Symbol: The ticker is a unique identifier for a security in the database. Where a company is delisted and the ticker subsequently recycled for use by a different company, we utilise that ticker for the currently active company and append a number to the ticker of the delisted company. The ACTIONS table provides a record of historical ticker changes.',
    `investorid` String COMMENT 'Institutional Investor Code: Six-character Sharadar investor id (retail holdings table).',
    `securitytype` LowCardinality(String) COMMENT 'Security Type: The available options to filter the SecurityType field are as follows: [SHR] Common Shares [FND] Fund Units [CLL] Call Options [PUT] Put Options [WNT] Warrants [DBT] Debt [PRF] Preferred Shares [UND] Unidentified Security Type',
    `date` Date COMMENT 'Calendar Date: Quarter-end date for the 13F filing (retail holdings table).',
    `value` Float64 COMMENT 'Value: Total USD value in millions.',
    `units` Float64 COMMENT 'Units: Number of units in thousands.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (date, ticker, investorid, securitytype)
SETTINGS index_granularity = 8192
COMMENT 'Institutional investor holdings from quarterly SEC Form 13F filings. Sourced from Sharadar SF3 / holdings table.';

-- SF3A: Sharadar US Institutional Investors Summary By Ticker Table
-- This table aggregates institutional ownership data from SF3 at the individual security (ticker) level.
-- It provides summaries such as the total number of institutional holders, total units held across various security types (shares, calls, puts),
-- and the total value of these holdings for each stock per quarter.
CREATE TABLE IF NOT EXISTS sf3a
(
    `date` Date COMMENT 'Calendar Date: Quarter-end date (retail holdings_ticker table).',
    `ticker` LowCardinality(String) COMMENT 'Ticker Symbol: The ticker is a unique identifier for a security in the database. Where a company is delisted and the ticker subsequently recycled for use by a different company, we utilise that ticker for the currently active company and append a number to the ticker of the delisted company. The ACTIONS table provides a record of historical ticker changes.',
    `name` String COMMENT 'Issuer Name: The name of the issuer.',
    `shrholders` Float64 COMMENT 'Number of Shareholders (Institutional): The number of shareholders.',
    `cllholders` Float64 COMMENT 'Number of Call holders (Institutional): The number of call holders.',
    `putholders` Float64 COMMENT 'Number of Put holders (institutional): The number of put holders.',
    `wntholders` Float64 COMMENT 'Number of Warrant holders (institutional): The number of warrant holders.',
    `dbtholders` Float64 COMMENT 'Number of Debt holders (institutional): The number of debt holders.',
    `prfholders` Float64 COMMENT 'Number of Preferred Stock holders (institutional): The number of preferred stock holders.',
    `fndholders` Float64 COMMENT 'Number of Fund holders (institutional): The number of fund holders.',
    `undholders` Float64 COMMENT 'Number of Unidentified Security type holders (institutional): The number of unidentified security type holders.',
    `shrunits` Float64 COMMENT 'Number of Share Units held (institutional): The total number of share units held.',
    `cllunits` Float64 COMMENT 'Number of Call Units held (institutional): The total number of call units held.',
    `putunits` Float64 COMMENT 'Number of Put Units held (institutional): The total number of put units held.',
    `wntunits` Float64 COMMENT 'Number of Warrant Units held (institutional): The total number of warrant units held.',
    `dbtunits` Float64 COMMENT 'Number of Debt Units held (institutional): The total number of debt units held.',
    `prfunits` Float64 COMMENT 'Number of Preferred Stock units held (institutional): The total number of preferred stock units held.',
    `fndunits` Float64 COMMENT 'Number of Fund units held (institutional): The total number of fund units held.',
    `undunits` Float64 COMMENT 'Number of Unidentified Security type units held (institutional): The total number of unidentified security type units held.',
    `shrvalue` Float64 COMMENT 'Value of Share units held (institutional): The total value of share units held.',
    `cllvalue` Float64 COMMENT 'Value of Call units held (institutional): The total value of call units held.',
    `putvalue` Float64 COMMENT 'Value of Put units held (institutional): The total value of put units held.',
    `wntvalue` Float64 COMMENT 'Value of Warrant units held (institutional): The total value of warrant units held.',
    `dbtvalue` Float64 COMMENT 'Value of Debt units held (institutional): The total value of debt units held.',
    `prfvalue` Float64 COMMENT 'Value of Preferred Stock units held (institutional): The total value of preferred stock units held.',
    `fndvalue` Float64 COMMENT 'Value of Fund units held (institutional): The total value of fund units held.',
    `undvalue` Float64 COMMENT 'Value of Unidentified Security type units held (institutional): The total value of unidentified security type units held.',
    `totalvalue` Float64 COMMENT 'Total Value of all Security types held (institutional): The total value of all security types held.',
    `percentoftotal` Float64 COMMENT 'Percentage of Total Institutional Holdings for the Quarter: The percentage that the [TotalValue] of this line item constitutes of all institutional holdings for this quarter.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192
COMMENT 'Aggregated institutional ownership data from SF3 at the individual security (ticker) level. Sourced from Sharadar SF3A / holdings_ticker table.';

-- SF3B: Sharadar US Institutional Investors Summary By Investor Table
-- This table aggregates institutional ownership data from SF3 at the individual investor level.
-- It provides summaries of each institutional manager's portfolio, including the number of distinct holdings, total units,
-- and total value across different security types (shares, calls, puts) per quarter.
CREATE TABLE IF NOT EXISTS sf3b
(
    `date` Date COMMENT 'Calendar Date: Quarter-end date (retail holdings_investor table).',
    `investorid` String COMMENT 'Institutional Investor Code: Six-character Sharadar investor id.',
    `investorname` String COMMENT 'Institutional Investor Name: Human-readable investor name.',
    `shrholdings` Float64 COMMENT 'Number of Distinct Share holdings (institutional): The number of distinct share holdings held by the institution.',
    `cllholdings` Float64 COMMENT 'Number of Distinct Call holdings (institutional): The number of distinct call holdings held by the institution.',
    `putholdings` Float64 COMMENT 'Number of Distinct Put holdings (institutional): The number of distinct put holdings held by the institution.',
    `wntholdings` Float64 COMMENT 'Number of Distinct Warrant holdings (institutional): The number of distinct warrant holdings held by the institution.',
    `dbtholdings` Float64 COMMENT 'Number of Distinct Debt holdings (institutional): The number of distinct debt holdings held by the institution.',
    `prfholdings` Float64 COMMENT 'Number of Distinct Preferred Stock holdings (institutional): The number of distinct preferred stock holdings held by the institution.',
    `fndholdings` Float64 COMMENT 'Number of Distinct Fund holdings (institutional): The number of distinct fund holdings held by the institution.',
    `undholdings` Float64 COMMENT 'Number of Distinct Unidentified Security type holdings (institutional): The number of distinct unidentified security types held by the institution.',
    `shrunits` Float64 COMMENT 'Number of Share Units held (institutional): The total number of share units held.',
    `cllunits` Float64 COMMENT 'Number of Call Units held (institutional): The total number of call units held.',
    `putunits` Float64 COMMENT 'Number of Put Units held (institutional): The total number of put units held.',
    `wntunits` Float64 COMMENT 'Number of Warrant Units held (institutional): The total number of warrant units held.',
    `dbtunits` Float64 COMMENT 'Number of Debt Units held (institutional): The total number of debt units held.',
    `prfunits` Float64 COMMENT 'Number of Preferred Stock units held (institutional): The total number of preferred stock units held.',
    `fndunits` Float64 COMMENT 'Number of Fund units held (institutional): The total number of preferred stock units held.',
    `undunits` Float64 COMMENT 'Number of Unidentified Security type units held (institutional): The total number of unidentified security type units held.',
    `shrvalue` Float64 COMMENT 'Value of Share units held (institutional): The total value of share units held.',
    `cllvalue` Float64 COMMENT 'Value of Call units held (institutional): The total value of call units held.',
    `putvalue` Float64 COMMENT 'Value of Put units held (institutional): The total value of put units held.',
    `wntvalue` Float64 COMMENT 'Value of Warrant units held (institutional): The total value of warrant units held.',
    `dbtvalue` Float64 COMMENT 'Value of Debt units held (institutional): The total value of debt units held.',
    `prfvalue` Float64 COMMENT 'Value of Preferred Stock units held (institutional): The total value of preferred stock units held.',
    `fndvalue` Float64 COMMENT 'Value of Fund units held (institutional): The total value of fund units held.',
    `undvalue` Float64 COMMENT 'Value of Unidentified Security type units held (institutional): The total value of unidentified security type units held.',
    `totalvalue` Float64 COMMENT 'Total Value of all Security types held (institutional): The total value of unidentified security type units held.',
    `percentoftotal` Float64 COMMENT 'Percentage of Total Institutional Holdings for the Quarter: The percentage that the [TotalValue] of this line item constitutes of all institutional holdings for this quarter.'
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (investorid, date)
SETTINGS index_granularity = 8192
COMMENT 'Aggregated institutional ownership data from SF3 at the individual investor level. Sourced from Sharadar SF3B / holdings_investor table.';

-- SP500: Sharadar S&P500 Constituents Table
-- This table tracks the constituents of the S&P 500 index over time.
-- It records additions to and removals from the index, as well as current members, providing a historical view of the index's composition.
CREATE TABLE IF NOT EXISTS sp500
(
    `date` Date COMMENT 'Date: The action date.',
    `action` LowCardinality(String) COMMENT 'Action: The available actions in this database are: current, added, removed and historical.\t',
    `ticker` LowCardinality(String) COMMENT 'Ticker Symbol: The ticker is a unique identifier for a security in the database. Where a company is delisted and the ticker subsequently recycled for use by a different company, we utilise that ticker for the currently active company and append a number to the ticker of the delisted company. The ACTIONS table provides a record of historical ticker changes.',
    `name` String COMMENT 'Issuer Name: The name of the issuer.',
    `contraticker` String COMMENT 'Contra Ticker Symbol: The contra ticker is the opposing ticker entry. It represents the ticker that has been removed where the action=added, and the ticker that has been added where the action=removed.',
    `contraname` String COMMENT 'Contra Issuer Name: The name of the contra issuer.',
    `note` String COMMENT 'Notes: Placeholder for notes and additional information regarding additions to and removals from the S&P500.',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Last Updated DateTime: Synthetic timestamp for deduplication in ReplacingMergeTree. Set to current time during data load.'
)
ENGINE = ReplacingMergeTree(lastupdated)
ORDER BY (ticker, action, date)
SETTINGS index_granularity = 8192
COMMENT 'Tracks the constituents of the S&P 500 index over time. Sourced from Sharadar SP500 constituents table.';
