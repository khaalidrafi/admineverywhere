Freshorama-এর জন্য admin panel বানানোর সময় আমার মতে সবচেয়ে গুরুত্বপূর্ণ বিষয় হলো—শুধু অর্ডার দেখার dashboard নয়, বরং Order Management + Customer Management + Inventory + Delivery Tracking + Sales Analytics—সবকিছু যেন এক জায়গা থেকে পরিচালনা করা যায়।

তোমরা যেহেতু নিজেরা অর্ডার confirm করবে, কাস্টমারের তথ্য নিয়ে কাজ করবে এবং পণ্য বিক্রি ও ডেলিভারি monitor করবে, তাই শুরু থেকেই এমনভাবে system বানানো উচিত, যাতে অর্ডার বাড়লেও ম্যানুয়ালি Excel বা খাতায় হিসাব রাখতে না হয়।

# ১. Freshorama Admin Panel-এর সম্পূর্ণ কাঠামো

Dashboard

আজকের বিক্রি, নতুন অর্ডার, pending confirmation, delivery status, due payment এবং stock alerts।

Order Management

নতুন অর্ডার, ফোনে confirmation, packing, dispatch, delivery, cancellation ও return।

Customer CRM

কাস্টমারের contact, address, order history, total spending, repeat purchase ও follow-up।

Products & Inventory

পণ্যের দাম, cost, stock, batch, expiry, low-stock alert এবং stock movement।

Delivery Management

Courier বা নিজস্ব delivery, tracking ID, delivery charge, delivered/failed status ও return।

Reports & Analytics

Product-wise sales, profit, customer retention, order source, monthly growth এবং exportable reports।

Automation & Settings

Automatic notifications, status update, data validation, staff permissions এবং activity log।

এখন কোন অংশে কী কী feature রাখা দরকার, সেটা বিস্তারিত দেখি।

# ২. Dashboard-এ কী কী থাকবে?

Dashboard খুলেই যেন ১০ সেকেন্ডে বুঝতে পারো Freshorama-র ব্যবসার অবস্থা কী।

FRESHORAMA · ADMIN OVERVIEW (MOCKUP)

আজকের Net Sales

# ৳ ১২,৪৫০

উদাহরণস্বরূপ

New Orders

# ১৮

উদাহরণস্বরূপ

Need Confirmation

# ৬

উদাহরণস্বরূপ

In Delivery

# ৯

উদাহরণস্বরূপ

Quick Actions

Pending Orders

Low Stock

এটি শুধু dashboard-এর concept; সংখ্যাগুলো বাস্তব Freshorama data নয়।

Dashboard-এ অন্তত এই KPI-গুলো রাখবে:

* Total Orders: মোট কতটি অর্ডার এসেছে।

* Confirmed Orders: কতটি অর্ডার confirm হয়েছে।

* Pending Orders: কতটি অর্ডার এখনো action-এর অপেক্ষায়।

* Delivered Orders: কতটি সফলভাবে পৌঁছেছে।

* Gross Sales: মোট বিক্রয়মূল্য।

* Net Sales: discount, cancellation ও return-এর মতো বিষয় হিসাব করে সংজ্ঞায়িত বিক্রির পরিমাণ।

* Estimated Profit: পণ্যের cost এবং প্রযোজ্য delivery, packaging ও অন্যান্য খরচ বাদ দিয়ে আনুমানিক লাভ।

* Outstanding Payments: কত টাকা এখনো পাওনা।

* Low Stock Products: কোন পণ্যের stock কমে এসেছে।

* Return/Failed Delivery Rate: কত শতাংশ অর্ডার ফেরত এসেছে বা delivery ব্যর্থ হয়েছে।

সময় অনুযায়ী Today, Last 7 Days, This Month এবং Custom Date Range দিয়ে filter করতে পারবে।

একটা গুরুত্বপূর্ণ বিষয়: বিক্রি, হাতে থাকা cash, customer due এবং profit—এগুলো চারটি আলাদা metric। Dashboard-এ এগুলো কখনো এক করে দেখাবে না।

# ৩. Order Management — সবচেয়ে গুরুত্বপূর্ণ অংশ

Freshorama-র website-এর core feature হওয়া উচিত একটি পরিষ্কার Order Lifecycle। কাস্টমার অর্ডার দিলেই সেটা সরাসরি delivery-তে চলে যাবে না; admin হিসেবে তোমরা প্রতিটি ধাপ control করবে।

১. New Order Received

Website থেকে অর্ডার তৈরি

২. Pending Confirmation

Admin অর্ডার যাচাই করবে, প্রয়োজনে ফোন করবে

৩. Confirmed / Cancelled

Customer, address, product ও payment যাচাই

৪. Processing & Packing

Stock reserve, product check ও packaging

৫. Ready to Ship → Shipped

Courier assignment / delivery person assignment

৬. Delivered

Delivery সম্পন্ন, payment reconciliation বাকি থাকতে পারে

এ ছাড়া আলাদা status হিসেবে `On Hold`, `Delivery Failed`, `Returned`, `Refunded` এবং `Payment Pending` রাখতে হবে। Payment status-কে delivery status-এর সঙ্গে এক field-এ রাখবে না।

## প্রতিটি Order-এর ভেতরে কী দেখাবে?

ORDER ID

## FR-2026-00125

Placed: 16 Oct 2026, 10:30 AM

Pending

Customer Details

Customer Name

Phone number · Previous orders · Customer type

Delivery Address

Division → District → Upazila/Thana → Area → Full address

Order Items

![](https://images.openai.com/static-rsc-4/GsCGe0T8KcIDlD4vMEj7oamime2_xlNXTnDDFGj_XHSxcZodgqkZmOsIYLQTp1k6fHe9DW8ABjvikA0qalls32abTbYPNrZpTyxS8-4E-jCu0bYTsX5f-qMXd5Vek64ZyFl0hRbpwifflTcIADetnC52BVPUYemDn2ncYxg-cKI?purpose=inline)

Freshorama Mixed Chatu

1 × 1 kg

### ৳320

![Herbata Czarna Orange Pekoe Liściasta 100 g | Stacja Bio](https://images.openai.com/static-rsc-4/PCivCNujnKp20u0IZeAxsKJVL-CanhhzGxMzDuv-RElT6Z53ta57gY6LYIPnXm50rSuhsgtX8_gXnpLN3oM9TVNTwzYuuR0KLcVLRdHSoWI4lMSqVa4ZH1XJtzMTJUx2TdSHb65He4W7xKDn4xuCvQ6JuDa_c9_9F2XRxxX_c-E?purpose=inline)

Freshorama Tea

1 × 500 g

### ৳280

Subtotal

৳600

Delivery Charge

৳80

Total Payable

## ৳680

এটি একটি কাল্পনিক order-detail design; product ও price উদাহরণ হিসেবে দেওয়া হয়েছে।

প্রতিটি অর্ডারে আরও থাকবে:

* Payment method: COD, bKash, Nagad বা Bank Transfer।

* Payment status: Unpaid, Pending Verification, Partially Paid, Paid, Refunded।

* Courier name, tracking ID এবং delivery charge।

* Admin notes: যেমন “কাস্টমার সন্ধ্যার পর ফোন দিতে বলেছেন”।

* Order source: Website, Facebook, WhatsApp, Campaign বা Manual Entry।

* Assigned staff এবং last updated time।

* Order status history: কে, কখন, কোন status পরিবর্তন করেছে।

### Admin-এর জন্য দরকারি button

`Call Customer` · `Confirm Order` · `Edit Order` · `Print Invoice` · `Assign Delivery` · `Mark Delivered` · `Cancel Order`

অর্ডার confirm করার আগে stock availability ও address যাচাইয়ের সুবিধা রাখবে। অর্ডার cancel হলে reserved stock release হবে; delivered order-এর payment ও delivery charge reconcile করার ব্যবস্থা থাকবে।

# ৪. Delivery tracking কীভাবে করবে?

দুটি উপায় রাখবে।

Option A — Manual delivery tracking

শুরুর দিকে নিজস্ব delivery person বা ছোট পরিসরে courier-এর মাধ্যমে অর্ডার পাঠালে admin নিজে status update করবে।

| Delivery status     | কখন ব্যবহার করবে                       |
| ------------------- | -------------------------------------- |
| Ready to Ship       | প্যাকিং শেষ                            |
| Shipped / Picked Up | Courier বা delivery person পণ্য নিয়েছে |
| In Transit          | পথে আছে, tracking পাওয়া গেলে           |
| Delivered           | কাস্টমার পণ্য পেয়েছেন                  |
| Delivery Failed     | পৌঁছানো যায়নি                          |
| Returned            | পণ্য ফেরত এসেছে                        |

Option B — Courier integration

ব্যবসা বড় হলে courier provider-এর API বা supported integration দিয়ে tracking update স্বয়ংক্রিয় করা যায়। Courier অনুযায়ী availability ও API access যাচাই করতে হবে।

এখানে একটি বিষয় জরুরি: `Mark Delivered` চাপলেই অর্ডারটি স্বয়ংক্রিয়ভাবে `Paid` হবে না। COD হলে delivery confirmation ও courier settlement মিলিয়ে payment complete করতে হবে।

# ৫. Customer Management (CRM)

Freshorama-র জন্য customer database খুব গুরুত্বপূর্ণ। কারণ একজন কাস্টমার একবার Chatu বা Tea কিনে চলে গেলেন, নাকি নিয়মিত কিনছেন—সেটা জানতে পারলে repeat sales বাড়ানোর পরিকল্পনা করা যাবে।

প্রতিটি customer profile-এ রাখবে:

* Customer ID, নাম ও ফোন নম্বর।

* Delivery address এবং প্রয়োজনে একাধিক saved address।

* প্রথম অর্ডার, সর্বশেষ অর্ডার এবং মোট অর্ডার সংখ্যা।

* মোট কেনাকাটা, গড় order value এবং lifetime spend।

* কোন পণ্য বেশি কেনেন—Chatu, Tea, Honey বা অন্য পণ্য।

* Cancelled/returned orders এবং delivery success rate।

* Customer acquisition source ও campaign।

* Consent/opt-out status: promotional message পেতে সম্মতি আছে কি না।

* Customer notes এবং follow-up history।

## Customer segmentation

New Customers

প্রথম অর্ডার করা কাস্টমার। অর্ডার সম্পন্ন হওয়ার পর feedback চাইতে পারো।

Repeat Customers

দুই বা তার বেশি সফল অর্ডার করেছেন। তাদের reorder experience সহজ করো।

Due for Reorder

আগের ক্রয় ও পণ্যের সম্ভাব্য ব্যবহারের সময় ধরে পুনরায় কেনার reminder-এর উপযুক্ত কাস্টমার।

High-Value Customers

যারা দীর্ঘমেয়াদে বেশি কেনাকাটা করেন; order frequency ও spending দিয়ে শনাক্ত করবে।

কাস্টমারের তথ্য যেন শুধু অনুমোদিত কাজেই ব্যবহার হয়। Password বা payment credentials সংরক্ষণ করবে না; access control, consent এবং data retention policy রাখবে। Promotional SMS বা WhatsApp message পাঠানোর আগে প্রযোজ্য নিয়ম ও সম্মতি নিশ্চিত করবে।

# ৬. Data কী format-এ রাখলে analysis সবচেয়ে ভালো হবে?

এটা তোমাদের জন্য খুবই গুরুত্বপূর্ণ সিদ্ধান্ত। আমার recommendation হলো: Website-এর মূল data relational database-এ রাখবে, আর analysis-এর জন্য CSV/Excel export ও dashboard reports রাখবে।

শুধু একটা বড় Excel sheet-এ সব তথ্য রাখলে পরে order, customer, product, payment এবং delivery মিলিয়ে analysis করতে সমস্যা হবে।

## Recommended data structure

Orders

order_id, customer_id, order_date, status, subtotal, discount, delivery_charge, total, source

Order Items

order_id, product_id, quantity, unit_price, unit_cost, line_discount

একটি order-এ যত পণ্য থাকবে, প্রতিটি পণ্যের জন্য আলাদা row।

Customers

customer_id, name, phone, address, consent

Products

product_id, SKU, name, category, cost, selling_price

Payments

payment_id, order_id, amount, method, status

Shipments

order_id, courier, tracking_id, delivery_status, fees

এখানে `order_id`, `customer_id` ও `product_id` দিয়ে আলাদা data একসঙ্গে যুক্ত করা যাবে। Payment বা shipment একাধিকবার update হলেও মূল order record নষ্ট হবে না।

## CSV/Excel export-এর নিয়ম

একই order-এ Chatu, Tea এবং Honey থাকলে analysis-এর জন্য `Order Items` export-এ তিনটি আলাদা row থাকবে। তবে customer-এর মোট সংখ্যা গণনার সময় `order_id` নয়, unique `customer_id` গণনা করতে হবে।

| Column           | Example    | কেন দরকার             |
| ---------------- | ---------- | --------------------- |
| `order_id`       | FR-000125  | অর্ডার শনাক্ত         |
| `order_date`     | 2026-10-16 | তারিখভিত্তিক analysis |
| `product_sku`    | CHATU-1KG  | পণ্য শনাক্ত           |
| `quantity`       | 2          | কত unit বিক্রি        |
| `unit_price`     | 320        | বিক্রয়মূল্য           |
| `unit_cost`      | 210        | পণ্যের খরচ            |
| `discount`       | 20         | ছাড়                   |
| `order_status`   | Delivered  | সফল অর্ডার শনাক্ত     |
| `payment_status` | Paid       | আদায় যাচাই            |
| `source`         | Facebook   | Marketing attribution |

উপরের দামগুলো format বোঝানোর উদাহরণ; বাস্তব product cost ও price তোমাদের database থেকে আসবে।

Data rules:

* Date: `YYYY-MM-DD HH:mm:ss` এবং timezone নির্ধারিত থাকবে।

* Currency: সব financial value BDT-তে সংরক্ষণ করবে।

* Phone: string হিসেবে রাখবে, যাতে শুরুতে `0` হারিয়ে না যায়।

* SKU: প্রতিটি পণ্যের unique code থাকবে।

* Empty value: জানা নেই আর প্রযোজ্য নয়—এই দুই অবস্থা আলাদা রাখবে।

* Deleted বা cancelled order-এর historical record যেন হারিয়ে না যায়।

# ৭. Data Automation — কী কী স্বয়ংক্রিয় করবে?

Automation মানে শুধু notification পাঠানো নয়। একই data বারবার হাতে লিখতে না হওয়া, ভুল কমানো এবং নিয়মিত কাজগুলো নিজে থেকে সম্পন্ন হওয়াই মূল লক্ষ্য।

১. New Order Alert

Website-এ order তৈরি হলে admin dashboard-এ notification এবং প্রয়োজনমতো email/অনুমোদিত messaging alert যাবে।

২. Automatic Status Workflow

Confirm করলে order `Confirmed` হবে; packing শেষ হলে `Ready to Ship` করা যাবে। Status change-এর সঙ্গে order history সংরক্ষিত হবে।

৩. Stock Automation

Order confirm/fulfill করার নির্ধারিত নিয়ম অনুযায়ী stock reserve ও deduct হবে। Cancel বা return হলে উপযুক্ত নিয়মে stock restore হবে।

৪. Customer Notifications

Order received, confirmed, shipped ও delivered—প্রাসঙ্গিক ধাপে message পাঠানো হবে। একই message যেন duplicate না যায়, সেই ব্যবস্থা থাকবে।

৫. Daily/Weekly Reports

প্রতিদিনের sales, pending orders, delivered orders, payment due ও low-stock report স্বয়ংক্রিয়ভাবে তৈরি হবে।

৬. Exception Alerts

Payment verification বাকি, order অনেকক্ষণ pending, stock insufficient অথবা delivery failed হলে admin-কে জানাবে।

একটা বিষয় খেয়াল রেখো: Order confirmation শুরুতে manual রাখাই ভালো। অটোমেশন তোমাদের কাজ সহজ করবে, কিন্তু কাস্টমারের সঙ্গে যাচাই ছাড়া সব order স্বয়ংক্রিয়ভাবে confirm করার দরকার নেই।

# ৮. Sales Analytics & Business Intelligence

Freshorama শুধু কত টাকা বিক্রি হলো তা নয়, কোন পণ্য লাভ করছে, কোন customer আবার কিনছে, আর কোন marketing channel থেকে ভালো order আসছে—এসবও জানতে চাইবে।

এই চারটি রিপোর্ট অবশ্যই রাখবে।

![eCommerce personalizado para qualquer indústria | Wix Studio](https://images.openai.com/static-rsc-4/5ztfr0pcpvjgFE4BwSEC24scBZV5fZ1Sin_En04vyde23adhltrFA5Qa1_luixuxBFU0Z9MBqMQIymgYgk_2sYYAFzxMLXj4xmfuvW3XlMdCyaBIf-qE5VYQzlY2VcdoD6uX0vR9k1cc0DzNn9Ukfx0J43E2RmIlXIBTQInd8Is?purpose=inline)

A. Sales Report

* Daily, weekly ও monthly sales

* Total orders এবং average order value

* Product/category-wise sales

* Discount, cancellation ও refund

* Sales growth বনাম আগের সময়কাল

![用Excel做出入库管理系统：搭建技巧及操作步骤指南\_云表官网-云表无代码企业级应用搭建平台,无代码开发平台轻松定制WMS,MES,SRM,进销存等](https://images.openai.com/static-rsc-4/O2gUeH_vEA__ki-xRa3KCAdhaQfC25mORi1QlhyhgOJ-FPhk7Tms1_UX01p2GZJPzMu4Yd_FSu6Pok9XFqcYPy5uU-eOTXF7KnMLlO31NcJ-UIL2WHzTFCG0nO0b6G2z8tIBmO1wK29PPTnjcePSwr3YSQCowzHHrNuHM5xdTFE?purpose=inline)

B. Product Profitability

* কোন SKU সবচেয়ে বেশি বিক্রি হয়

* কোন পণ্যে gross margin বেশি

* Packaging ও delivery cost-এর প্রভাব

* Slow-moving stock

* Stock-out frequency

![Create Ecommerce Dashboard: New Customization Features | Peel Insights](https://images.openai.com/static-rsc-4/3BEEfHz8FHiNQ8RUvYsr0CK_FBrivZcveIMTxxKdWNmFdqltwqWoW9ZKFLeZNf9MFI7edLPt8sVUTDqOg2ziO5aSIXDZOHSu2x4x_nQcwoEizXXpfflz8No8-j-n0M0P6RgSpbszs318rYRRsIhMy83acClRGU-cwIWr9Q7ZVog?purpose=inline)

C. Customer Report

* New বনাম repeat customers

* Repeat purchase rate

* Average customer spending

* Customer acquisition source

* Last purchase অনুযায়ী reorder opportunity

![Shopify Dashboard: Ultimate Guide to Analytics & Store Performance](https://images.openai.com/static-rsc-4/88G8G6uUqh4nhZ_PE-UF7QPw4aMIqzl9rvpT3sBIQglMcT7HLLpCf2LhdKf2yxk8zbQtUyq0KZD5Dyfrmv5W4yvi6vbVRrptSd3eM0vD-xJfM68qsBLVyhkc2e3kYY-Ac2EIlYwcEX2xnqcCKK1KjvRkqlUWchsQpYNICbcheQY?purpose=inline)

D. Marketing Report

* Website বনাম Facebook/WhatsApp orders

* Campaign-wise confirmed sales

* Cancellation ও delivery success by source

* Campaign cost এবং customer acquisition cost

* Campaign থেকে প্রকৃত লাভ

এখানে কিছু metric-এর সংজ্ঞা ঠিক করে নিতে হবে।

* Gross margin = (Net product sales − COGS) ÷ Net product sales × 100%

* Average order value (AOV) = নির্বাচিত সময়ের eligible sales ÷ eligible orders

* Repeat purchase rate = নির্ধারিত সময়ের মধ্যে পুনরায় কেনা customer ÷ সেই সময়ের eligible customers × 100%

* Customer acquisition cost (CAC) = নির্দিষ্ট সময়ে নতুন customer আনতে marketing ও acquisition-এর খরচ ÷ নতুন acquired customers

সব রিপোর্টে একই সংজ্ঞা ব্যবহার করবে। Cancelled ও returned order-কে delivered sales-এর সঙ্গে মিশিয়ে ফেলবে না।

# ৯. Inventory ও Finance একসঙ্গে কীভাবে কাজ করবে?

Freshorama-র মতো food business-এ product inventory শুধু quantity দিয়ে শেষ নয়। পণ্যের batch, expiry এবং ক্রয়মূল্যও কাজে লাগবে।

Inventory module-এ রাখবে:

* SKU, product name, unit (g/kg/packet/jar)।

* Opening stock, purchase/production entry, sold quantity, returned quantity, closing stock।

* Supplier, batch number, purchase date ও expiry date যেখানে প্রযোজ্য।

* Minimum stock threshold ও low-stock notification।

* Damaged/expired stock adjustment-এর কারণ।

* Stock adjustment কে করেছেন এবং কখন করেছেন।

Finance module-এ রাখবে:

* Order-wise sales এবং payment collection।

* COD collection ও courier settlement।

* Delivery, packaging, discount ও refund।

* Product purchase cost, operating expense এবং salary।

* Customer receivable এবং supplier payable।

* Daily cash/bank/mobile financial service reconciliation।

একটি গুরুত্বপূর্ণ পার্থক্য: delivered order-এর sales revenue আর হাতে পাওয়া cash এক জিনিস নয়। আর inventory-তে কত টাকা আটকে আছে, সেটাও profit নয়।

# ১০. Admin permissions ও security

সব admin-কে সব ক্ষমতা দেওয়ার দরকার নেই।

| Role              | Access                                   |
| ----------------- | ---------------------------------------- |
| Super Admin       | সব setting, staff, reports ও permissions |
| Order Manager     | Order, customer ও delivery management    |
| Inventory Manager | Stock, batch, supplier ও purchase        |
| Accounts          | Payment, expenses, due ও reconciliation  |
| Analyst           | Read-only reports ও approved exports     |

এর সঙ্গে অবশ্যই থাকবে:

* Secure login ও password reset।

* Role-based permissions।

* Important action-এর audit log।

* Database backup ও recovery plan।

* Customer data export/download permission।

* Payment status বা order history পরিবর্তনের record।

* Sensitive customer information সীমিত staff-এর কাছে দৃশ্যমান রাখা।

# ১১. কোন feature আগে বানাবে?

সবকিছু একসঙ্গে বানাতে গেলে development time ও cost বাড়তে পারে। তাই আমি তিনটি phase-এ এগোতে বলব।

Phase 1

অবশ্যই প্রথম version-এ

Dashboard, Order Management, manual confirmation, customer profiles, product catalogue, stock, payment status, delivery tracking, CSV export, admin roles ও backup।

Phase 2

Business operations উন্নত করা

Courier integration, automated notifications, batch/expiry tracking, purchase management, expenses, customer segmentation, repeat-purchase reports এবং profit analytics।

Phase 3

Advanced automation

Campaign attribution, customer cohort analysis, reorder reminders, forecasting, automated reconciliation এবং advanced business intelligence।

## ১২. Developer-কে দেওয়ার জন্য final checklist

## Development checklist

Developer-এর সঙ্গে feature ধরে ধরে review করো।

## 0/15

Core Admin

Dashboard with date filters

Order list with search and status filters

Order detail and manual confirmation

Order status history and staff assignment

Customer CRM and order history

Operations

Products, SKU and pricing

Stock reservation and movement history

Delivery assignment and tracking

Payment collection and refund records

Expenses, due and reconciliation

Data & Automation

Relational database with unique IDs

CSV/Excel export with consistent fields

Sales, product and customer reports

Notifications and exception alerts

Role-based access, audit log and backup

Copy checklistCopy for developer

## আমার শেষ পরামর্শ

Freshorama-র জন্য admin panel-কে মূলত তিনটি প্রশ্নের উত্তর দিতে হবে:

1. Order: কোন অর্ডারে এখন কী action দরকার?

2. Money: কত বিক্রি হয়েছে, কত টাকা আদায় হয়েছে, কত পাওনা এবং প্রকৃত লাভ কত?

3. Growth: কোন পণ্য, customer এবং marketing channel ব্যবসাকে এগিয়ে নিচ্ছে?

তবে তোমাদের জন্য আরও নির্দিষ্ট architecture ঠিক করতে একটা তথ্য জানা দরকার।