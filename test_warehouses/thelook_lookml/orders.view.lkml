view: orders {
  dimension: id {
    primary_key: yes
    type: number
    sql: ${TABLE}.id ;;
  }

  dimension_group: created {
    type: time
    timeframes: [
      raw,
      time,
      date,
      week,
      month,
      quarter,
      year
    ]
    sql: ${TABLE}.created_at ;;
  }

  dimension: status {
    type: string
    sql: ${TABLE}.status ;;
  }

  dimension: traffic_source {
    type: string
    sql: ${TABLE}.traffic_source ;;
  }

  dimension: user_id {
    type: number
    # hidden: yes
    sql: ${TABLE}.user_id ;;
  }

  dimension: total_amount_of_order_usd {
    type: number
    value_format_name: decimal_2
    sql:
      (SELECT SUM(order_items.sale_price)
      FROM order_items
      WHERE order_items.order_id = ${id}) ;;
  }

  dimension: total_cost_of_order {
    type: number
    value_format_name: decimal_2
    sql:
        (SELECT SUM(inventory_items.cost)
        FROM order_items
        LEFT JOIN inventory_items ON order_items.inventory_item_id = inventory_items.id
        WHERE order_items.order_id = ${id}) ;;
  }

  dimension: order_profit {
    type: number
    value_format_name: decimal_2
    sql: ${total_amount_of_order_usd} - ${total_cost_of_order} ;;
  }

  dimension: order_sequence_number {
    type: number
    sql:
      (SELECT COUNT(*)
      FROM orders o
      WHERE o.id < ${TABLE}.id
      AND o.user_id = ${TABLE}.user_id) + 1
      ;;
  }

  dimension: is_first_purchase {
    type: yesno
    sql: ${order_sequence_number} = 1 ;;
  }

  measure: count {
    type: count
    drill_fields: [id, users.last_name, users.first_name, users.id, order_items.count]
  }

  measure: first_purchase_count {
    type: count
    drill_fields: [id, created_time, users.name, users.history, total_cost_of_order]
    filters: {
      field: is_first_purchase
      value: "Yes"
    }
  }

  measure: average_order_profit {
    type: average
    value_format: "$#.00"
    sql: ${order_profit} ;;
  }
}
