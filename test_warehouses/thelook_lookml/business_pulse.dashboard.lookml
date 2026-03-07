- dashboard: business_pulse
  title: "Business Pulse"
  layout: newspaper
  preferred_viewer: dashboards-next
  rows:
    - elements: [total_orders, average_order_profit, first_purchasers]
      height: 220
    - elements: [orders_by_day_and_category, sales_by_date]
      height: 400
    - elements: [top_zip_codes, sales_state_map]
      height: 400
    - elements: [sales_by_date_and_category, top_15_brands]
      height: 400
    - elements: [cohort_title]
      height: 50
    - elements: [layer_cake_cohort]
      height: 400
    - elements: [customer_cohort]
      height: 400

  filters:

  - name: date
    title: "Date"
    type: date_filter
    default_value: Last 90 Days

  - name: state
    title: 'State / Region'
    type: field_filter
    explore: users
    field: users.state

  elements:

  - name: total_orders
    type: single_value
    explore: orders
    measures: [orders.count]
    listen:
      date: orders.created_date
      state: users.state
    font_size: medium

  - name: average_order_profit
    type: single_value
    explore: orders
    measures: [orders.average_order_profit]
    listen:
      date: orders.created_date
      state: users.state
    font_size: medium

  - name: first_purchasers
    type: single_value
    explore: orders
    measures: [orders.first_purchase_count]
    listen:
      date: orders.created_date
      state: users.state
    font_size: medium

  - name: orders_by_day_and_category
    title: "Orders by Day and Category"
    type: looker_area
    explore: order_items
    dimensions: [orders.created_date]
    pivots: [products.category]
    measures: [order_items.count]
    filters:
      products.category: Blazers & Jackets, Sweaters, Pants, Shorts, Fashion Hoodies & Sweatshirts, Accessories
    listen:
      date: orders.created_date
      state: users.state
    sorts: [orders.created_date]
    limit: 500
    colors: ["#651F81", "#80237D", "#C488DD", "#Ef7F0F", "#FEAC47", "#8ED1ED"]
    legend_align:
    y_axis_labels: "# Order Items"
    stacking: normal
    x_axis_datetime: yes
    hide_points: yes
    hide_legend: yes
    x_axis_datetime_tick_count: 4
    show_x_axis_label: false

  - name: sales_by_date
    type: looker_column
    explore: order_items
    dimensions: [orders.created_date]
    measures: [order_items.total_sale_price]
    listen:
      state: users.state
      date: orders.created_date
    sorts: [orders.created_date]
    limit: 30
    colors: ["#651F81"]
    reference_lines:
      - value: [max, mean]
        label: Above Average
        color: "#Ef7F0F"
      - value: 20000
        label: Target
        color: "#Ef7F0F"
      - value: [median]
        label: Median
        color: "#Ef7F0F"
    x_axis_scale: time
    x_axis_datetime_tick_count: 4
    y_axis_labels: "Total Sale Price ($)"
    y_axis_combined: yes
    show_x_axis_label: false
    hide_legend: yes
    hide_points: yes

  - name: top_zip_codes
    type: looker_geo_coordinates
    map: usa
    explore: order_items
    dimensions: [users.zipcode]
    measures: [order_items.count]
    colors: [gold, orange, darkorange, orangered, red]
    listen:
      date: orders.created_date
      state: users.state
    point_color: "#651F81"
    point_radius: 3
    sorts: [order_items.count desc]
    limit: 500

  - name: sales_state_map
    title: "Sales by State"
    type: looker_geo_choropleth
    map: usa
    explore: order_items
    dimensions: [users.state]
    measures: [order_items.count]
    colors: "#651F81"
    sorts: [order_items.total_sale_price desc]
    listen:
      date: orders.created_date
      state: users.state
    limit: 500

  - name: top_15_brands
    type: table
    explore: order_items
    dimensions: [products.brand]
    measures: [order_items.count, order_items.total_sale_price, order_items.average_sale_price]
    listen:
      date: orders.created_date
      state: users.state
    sorts: [order_items.count desc]
    limit: 15

  - name: sales_by_date_and_category
    title: "Sales by Date and Category"
    type: looker_donut_multiples
    explore: order_items
    dimensions: [orders.created_week]
    pivots: [products.category]
    measures: [order_items.count]
    listen:
      date: orders.created_date
      state: users.state
    filters:
      products.category: Accessories, Active, Blazers & Jackets, Clothing Sets
    sorts: [orders.created_week desc]
    colors: ["#651F81","#EF7F0F","#555E61","#2DA7CE"]
    limit: 24
    charts_across: 3
    show_value_labels: true

  - name: cohort_title
    type: text
    title_text: 'Orders By Sign Up Month For The Last 12 Months'

  - name: layer_cake_cohort
    title: "Layered Cohort"
    type: looker_area
    explore: orders
    dimensions: [orders.created_month]
    pivots: [users.created_month]
    measures: [orders.count]
    filters:
      orders.created_month: 12 months ago for 12 months
      users.created_month: 12 months ago for 12 months
    sorts: [orders.created_month]
    limit: 500
    y_axis_labels: ["Number of orders"]
    x_axis_label: "Order Month"
    legend_align: right
    colors: ["#FF0000","#DE0000","#C90000","#9C0202","#800101","#6B0000","#4D006B","#0D0080","#080054","#040029","#000000"]
    stacking: normal
    hide_points: yes

  - name: customer_cohort
    title: "Tabular Cohort"
    type: table
    explore: orders
    dimensions: [orders.created_month]
    pivots: [users.created_month]
    measures: [orders.count]
    filters:
      orders.created_month: 12 months ago for 12 months
      users.created_month: 12 months ago for 12 months
    sorts: [orders.created_month]
    limit: 500
    total: true
    row_total: right
