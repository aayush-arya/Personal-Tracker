import datetime
import json
from dataclasses import dataclass
from collections import defaultdict
import csv
import re
from flask import Flask, request, redirect, url_for, render_template_string

# --- 1. Data Structures (Dataclasses) ---

@dataclass
class Expense:
    """Represents a single expense item, now including an optional tag/sub-category."""
    amount: float
    category: str
    date: str # Stored as YYYY-MM-DD string
    tag: str = "" 

    def to_dict(self):
        return {'amount': self.amount, 'category': self.category, 'date': self.date, 'tag': self.tag}

    @staticmethod
    def from_dict(data):
        return Expense(
            amount=data['amount'], 
            category=data['category'], 
            date=data['date'],
            tag=data.get('tag', "")
        )

@dataclass
class Income:
    """Represents a single income item."""
    amount: float
    source: str
    date: str 

    def to_dict(self):
        return {'amount': self.amount, 'source': self.source, 'date': self.date}

    @staticmethod
    def from_dict(data):
        return Income(data['amount'], data['source'], data['date'])

# --- 2. Data Persistence (DataManager) ---

class DataManager:
    """Handles loading and saving of expense, budget, and income data."""
    FILEPATH = 'expenses.json'

    def load_data(self):
        data = {'expenses': [], 'budgets': {}, 'incomes': []}
        try:
            with open(self.FILEPATH, 'r') as f:
                loaded_data = json.load(f)
                
                expense_dicts = loaded_data.get('expenses', [])
                data['expenses'] = [Expense.from_dict(d) for d in expense_dicts]
                
                income_dicts = loaded_data.get('incomes', [])
                data['incomes'] = [Income.from_dict(d) for d in income_dicts]

                data['budgets'] = loaded_data.get('budgets', {})
                
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            return data
        except Exception as e:
            return data

    def save_data(self, expenses: list[Expense], budgets: dict, incomes: list[Income]):
        try:
            data_to_save = {
                'expenses': [exp.to_dict() for exp in expenses],
                'budgets': budgets,
                'incomes': [inc.to_dict() for inc in incomes]
            }
            with open(self.FILEPATH, 'w') as f:
                json.dump(data_to_save, f, indent=4)
        except Exception:
            pass # Suppress saving errors for web demo

# --- 3. Core Logic (ExpenseTracker) ---

class ExpenseTracker:
    """Manages expenses, budgeting, reporting, and utility features."""
    def __init__(self):
        self.data_manager = DataManager()
        loaded_data = self.data_manager.load_data()
        
        self.expenses = loaded_data['expenses']
        self.budgets = loaded_data['budgets']
        self.incomes = loaded_data['incomes']

    def _save(self):
        """Helper to save all data after any modification."""
        self.data_manager.save_data(self.expenses, self.budgets, self.incomes)

    # --- Expense/Income Management ---

    def add_expense(self, amount: float, category: str, date_str: str, tag: str = ""):
        """Logs a new expense and returns any budget alert message."""
        category_cleaned = category.strip().capitalize()
        tag_cleaned = tag.strip()
        
        try:
            expense = Expense(
                amount=amount,
                category=category_cleaned,
                date=date_str,
                tag=tag_cleaned
            )
            self.expenses.append(expense)
            self._save()
            
            # BUDGET ALERT CHECK
            alert_message = ""
            if category_cleaned in self.budgets:
                budget_limit = self.budgets[category_cleaned]
                monthly_spending = self._get_category_spending() 
                current_spent = monthly_spending.get(category_cleaned, 0.0)
                
                if current_spent > budget_limit:
                    over_amount = current_spent - budget_limit
                    alert_message = f"🚨 BUDGET ALERT: Spending in {category_cleaned} exceeds budget of ${budget_limit:,.2f} by ${over_amount:,.2f}!"
            
            return True, "Expense added successfully." + (f" {alert_message}" if alert_message else "")
                
        except Exception as e:
            return False, f"Failed to add expense: {e}"

    def add_income(self, amount: float, source: str, date_str: str):
        """Logs a new income item."""
        source_cleaned = source.strip().capitalize()
        try:
            income = Income(amount=amount, source=source_cleaned, date=date_str)
            self.incomes.append(income)
            self._save()
            return True, f"Income added successfully from {source_cleaned}."
        except Exception as e:
            return False, f"Failed to add income: {e}"
            
    def set_budget(self, category: str, amount: float):
        """Sets or updates the monthly budget limit for a category."""
        category_cleaned = category.strip().capitalize()
        self.budgets[category_cleaned] = amount
        self._save()
        return True, f"Budget set: Monthly limit for {category_cleaned} is now ${amount:,.2f}"

    def remove_expense(self, index: int):
        """Removes an expense by its index."""
        try:
            if 0 <= index < len(self.expenses):
                removed_expense = self.expenses.pop(index)
                self._save()
                return True, f"Expense on {removed_expense.date} for ${removed_expense.amount:,.2f} ({removed_expense.category}) removed successfully."
            else:
                return False, "Invalid expense index."
        except Exception as e:
            return False, f"Failed to remove expense: {e}"

    def remove_income(self, index: int):
        """Removes an income by its index."""
        try:
            if 0 <= index < len(self.incomes):
                removed_income = self.incomes.pop(index)
                self._save()
                return True, f"Income on {removed_income.date} from {removed_income.source} (${removed_income.amount:,.2f}) removed successfully."
            else:
                return False, "Invalid income index."
        except Exception as e:
            return False, f"Failed to remove income: {e}"

    def delete_budget(self, category_name: str):
        """Removes the monthly budget limit for a category."""
        category_cleaned = category_name.strip().capitalize()

        if category_cleaned in self.budgets:
            del self.budgets[category_cleaned]
            self._save()
            return True, f"Budget limit for '{category_cleaned}' removed successfully."
        else:
            return False, f"No budget found for category '{category_cleaned}'."


    def delete_category(self, category_name: str):
        """Removes all expenses and the budget for a specific category."""
        category_cleaned = category_name.strip().capitalize()
        
        original_count = len(self.expenses)
        
        # 1. Delete all associated expenses
        self.expenses = [exp for exp in self.expenses if exp.category != category_cleaned]
        deleted_count = original_count - len(self.expenses)

        # 2. Delete the associated budget
        budget_deleted = False
        if category_cleaned in self.budgets:
            del self.budgets[category_cleaned]
            budget_deleted = True

        self._save()
        
        message = f"Category '{category_cleaned}' deleted. Removed {deleted_count} expense(s)."
        if budget_deleted:
            message += " Budget limit also removed."
        
        if deleted_count == 0 and not budget_deleted:
            return False, f"Category '{category_cleaned}' not found in expenses or budgets."
        
        return True, message

    # --- Reporting/Viewing ---

    def _filter_transactions(self, records, filter_type: str = 'all'):
        """Helper to filter a list of records (expenses/incomes) by time period."""
        if filter_type == 'all':
            return records
        
        current_date = datetime.date.today()
        
        if filter_type == 'month':
            filter_str = current_date.strftime('%Y-%m')
            return [r for r in records if r.date.startswith(filter_str)]
        
        if filter_type == 'year':
            filter_str = current_date.strftime('%Y')
            return [r for r in records if r.date.startswith(filter_str)]
            
        return records


    def get_expenses_summary(self):
        """Returns the list of all expenses, sorted by date."""
        # Use enumerate to associate an index with each expense
        indexed_expenses_with_original_index = list(enumerate(self.expenses))
        
        # Sort by date, newest first
        sorted_expenses = sorted(
            indexed_expenses_with_original_index, 
            key=lambda item: item[1].date, 
            reverse=True
        )

        indexed_for_table = [(original_index, expense) for original_index, expense in sorted_expenses]
        
        total_spent = sum(exp.amount for exp in self.expenses)
        return indexed_for_table, total_spent
    
    def get_income_summary(self):
        """Returns the list of all incomes, sorted by date and indexed for deletion."""
        indexed_incomes_with_original_index = list(enumerate(self.incomes))
        
        # Sort by date, newest first
        sorted_incomes = sorted(
            indexed_incomes_with_original_index, 
            key=lambda item: item[1].date, 
            reverse=True
        )

        # Map to (original_index, income_object)
        indexed_for_table = [(original_index, income) for original_index, income in sorted_incomes]
        
        total_income = sum(inc.amount for inc in self.incomes)
        return indexed_for_table, total_income


    def get_combined_logs(self):
        """Combines expenses and incomes into a single list, sorted by date."""
        
        # Format expenses for combined view
        expenses_for_log = [{
            'date': exp.date,
            'amount': exp.amount,
            'description': f"{exp.category}: {exp.tag}" if exp.tag else exp.category,
            'type': 'Expense',
            'amount_class': 'negative'
        } for exp in self.expenses]

        # Format incomes for combined view
        incomes_for_log = [{
            'date': inc.date,
            'amount': inc.amount,
            'description': inc.source,
            'type': 'Income',
            'amount_class': 'positive'
        } for inc in self.incomes]

        combined_logs = expenses_for_log + incomes_for_log
        
        # Sort combined logs by date, newest first
        combined_logs_sorted = sorted(combined_logs, key=lambda item: item['date'], reverse=True)
        
        return combined_logs_sorted

    def get_category_chart_data(self, time_filter='all'):
        """Calculates total spending grouped by category based on time_filter."""
        filtered_expenses = self._filter_transactions(self.expenses, time_filter)
        
        spending_map = defaultdict(float)
        for exp in filtered_expenses:
            spending_map[exp.category] += exp.amount
            
        labels = list(spending_map.keys())
        data = list(spending_map.values())
        
        return {'labels': labels, 'data': data}

    def get_monthly_trend_data(self, time_filter='all'):
        """Calculates total spending grouped by month/year based on time_filter."""
        filtered_expenses = self._filter_transactions(self.expenses, time_filter)
        
        # Group spending by YYYY-MM
        monthly_spending = defaultdict(float)
        for exp in filtered_expenses:
            monthly_key = exp.date[:7] # YYYY-MM
            monthly_spending[monthly_key] += exp.amount
            
        # Sort keys (YYYY-MM) and create parallel lists for Chart.js
        sorted_months = sorted(monthly_spending.keys())
        
        labels = []
        data = []
        
        for month_key in sorted_months:
            # Format label nicely for the chart (e.g., 'Aug 2025')
            try:
                date_obj = datetime.datetime.strptime(month_key, '%Y-%m')
                labels.append(date_obj.strftime('%b %Y'))
            except ValueError:
                labels.append(month_key)
                
            data.append(monthly_spending[month_key])
            
        return {'labels': labels, 'data': data}


    def _get_category_spending(self):
        """Calculates total spending grouped by category for the current month."""
        current_month = datetime.date.today().strftime('%Y-%m')
        monthly_spending = defaultdict(float)
        
        for exp in self.expenses:
            if exp.date[:7] == current_month:
                monthly_spending[exp.category] += exp.amount
                
        return monthly_spending

    def calculate_net_savings(self):
        """Calculates net savings (Income - Expenses) for the current month."""
        current_month = datetime.date.today().strftime('%Y-%m')
        
        # 1. Calculate Monthly Income
        total_income = sum(inc.amount for inc in self.incomes if inc.date[:7] == current_month)
                
        # 2. Calculate Monthly Expenses
        total_expense = sum(exp.amount for exp in self.expenses if exp.date[:7] == current_month)
        
        net_savings = total_income - total_expense
        
        return total_income, total_expense, net_savings

    def get_budget_report(self):
        """Returns data for the monthly budget report."""
        spending = self._get_category_spending()
        report_data = []

        # Combine all categories that have a budget OR have spending this month
        categories = sorted(list(set(self.budgets.keys()) | set(spending.keys())))
        
        for category in categories:
            budget = self.budgets.get(category, 0.0)
            spent = spending.get(category, 0.0)
            remaining = budget - spent
            
            if spent > budget and budget > 0:
                status = "OVER BUDGET"
                status_class = "negative"
            elif budget == 0:
                status = "NO BUDGET SET"
                status_class = ""
            else:
                status = "On Track"
                status_class = "positive"
            
            report_data.append({
                'category': category,
                'budget': budget,
                'spent': spent,
                'remaining': remaining,
                'status': status,
                'status_class': status_class
            })
            
        return report_data


# --- 4. Flask Application Setup ---

app = Flask(__name__)
tracker = ExpenseTracker()

# --- HTML Template (Using a single string variable for single-file constraint) ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Personal Finance Tracker</title>
    <style>
        body { 
            font-family: 'Inter', sans-serif; 
            background-color: #e8f0f7; /* Very light blue-grey */
            color: #333; 
            margin: 0; 
            padding: 20px; 
        }
        .container { 
            max-width: 1200px; 
            margin: 0 auto; 
            background-color: #ffffff; 
            padding: 30px; 
            border-radius: 12px; 
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.1); /* Enhanced Shadow */
        }
        h1 { 
            color: #004d99; /* Deep Navy Blue */
            text-align: center; 
            margin-bottom: 30px; 
        }
        h2 {
            color: #0077b6; /* Mid Blue */
            margin-top: 0;
        }
        .card { 
            background: #f8fbff; /* Very light background for cards */
            border-radius: 8px; 
            padding: 20px; 
            margin-bottom: 20px; 
            border: 1px solid #d0e0f0; /* Subtle border */
        }
        .form-grid { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
            gap: 15px; 
        }
        .form-grid label { 
            display: block; 
            margin-bottom: 5px; 
            font-weight: 600; 
        }
        .form-grid input, .form-grid select { 
            width: 100%; 
            padding: 10px; 
            border: 1px solid #ccc; 
            border-radius: 6px; 
            box-sizing: border-box; 
        }
        .btn-submit { 
            background-color: #00a896; /* Vibrant Teal/Green */
            color: white; 
            padding: 10px 20px; 
            border: none; 
            border-radius: 6px; 
            cursor: pointer; 
            font-weight: bold; 
            grid-column: 1 / -1; 
            margin-top: 10px; 
            transition: background-color 0.3s;
        }
        .btn-submit:hover { 
            background-color: #008779; 
        }
        .btn-delete {
            background-color: #dc3545; /* Red for deletion */
            color: white;
            padding: 5px 10px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-weight: normal;
            transition: background-color 0.3s;
            font-size: 0.85em;
        }
        .btn-delete:hover {
            background-color: #c82333;
        }
        .message { 
            padding: 10px; 
            border-radius: 6px; 
            margin-bottom: 15px; 
            font-weight: bold; 
        }
        /* UPDATED SUCCESS STYLING FOR BETTER NOTIFICATION CONTRAST */
        .success { 
            background-color: #e0f7fa; /* Light Cyan/Teal */
            color: #0077b6; /* Mid Blue for text */
            border: 1px solid #b2ebf2; 
        }
        .alert { 
            background-color: #f8d7da; 
            color: #721c24; 
            border: 1px solid #f5c6cb; 
        }
        table { 
            width: 100%; 
            border-collapse: collapse; 
            margin-top: 20px; 
        }
        th, td { 
            padding: 12px 15px; 
            text-align: left; 
            border-bottom: 1px solid #dee2e6; 
        }
        th { 
            background-color: #0077b6; /* Professional Blue */
            color: white; 
            font-weight: 500;
        }
        .total-row td { 
            background-color: #f8f9fa; 
            font-weight: bold; 
            border-top: 2px solid #004d99; /* Deep Navy Separator */
        }
        .tab-menu { 
            display: flex; 
            justify-content: center; 
            margin-bottom: 20px; 
        }
        .tab-menu a { 
            padding: 10px 20px; 
            text-decoration: none; 
            color: #0077b6; 
            border-radius: 6px; 
            margin: 0 5px; 
            transition: background-color 0.3s, color 0.3s; 
            border: 1px solid transparent;
        }
        .tab-menu a:hover {
            background-color: #d0e0f0;
        }
        .tab-menu a.active { 
            background-color: #0077b6; 
            color: white;
            border-color: #0077b6;
        }
        .filter-btn-group {
            display: flex;
            justify-content: center;
            gap: 10px;
            margin-bottom: 20px;
        }
        .filter-btn-group a {
            padding: 8px 15px;
            border: 1px solid #0077b6;
            color: #0077b6;
            text-decoration: none;
            border-radius: 4px;
            transition: background-color 0.2s;
        }
        .filter-btn-group a.active {
            background-color: #0077b6;
            color: white;
        }
        .report-box { 
            text-align: center; 
            padding: 30px; 
            border: 2px solid #004d99; /* Deep Navy Border */
            border-radius: 10px; 
            margin-top: 30px; 
            background-color: #ffffff;
        }
        .report-box h3 { 
            margin-top: 0; 
            color: #004d99; 
        }
        .report-box .amount { 
            font-size: 2.5em; 
            font-weight: bold; 
            margin: 10px 0; 
        }
        .positive { 
            color: #00a896; /* Teal/Green */
        }
        .negative { 
            color: #dc3545; /* Standard Red for Loss */
        }
        .budget-report td { font-weight: 600; }
        .budget-report .positive { color: #155724; }
        .budget-report .negative { color: #721c24; }
        .chart-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-top: 20px;
        }
        @media (max-width: 900px) {
            .chart-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Personal Finance Tracker</h1>
        
        <div class="tab-menu">
            <a href="{{ url_for('index') }}" class="{{ 'active' if active_tab == 'summary' else '' }}">Expenses & Income</a>
            <a href="{{ url_for('income_management') }}" class="{{ 'active' if active_tab == 'income_mgmt' else '' }}">Income Management</a>
            <a href="{{ url_for('combined_logs') }}" class="{{ 'active' if active_tab == 'logs' else '' }}">Transaction Log</a>
            <a href="{{ url_for('net_savings_report') }}" class="{{ 'active' if active_tab == 'savings' else '' }}">Net Savings Report</a>
            <a href="{{ url_for('budgeting_page') }}" class="{{ 'active' if active_tab == 'budgeting' else '' }}">Budgeting</a>
            <a href="{{ url_for('visualization_page') }}" class="{{ 'active' if active_tab == 'visualization' else '' }}">Visualization</a>
        </div>
        
        {% if message %}
        <div class="message {{ 'success' if success else 'alert' }}">{{ message | safe }}</div>
        {% endif %}

        {{ content | safe }}
    </div>
</body>
</html>
"""

# --- Jinja2-style content blocks for rendering data ---

def get_expense_form_html():
    """Returns the HTML form for adding a new expense."""
    return """
        <div class="card">
            <h2>💸 Add New Expense</h2>
            <form method="POST" action="{{ url_for('add_record') }}">
                <input type="hidden" name="type" value="expense">
                <div class="form-grid">
                    <div>
                        <label for="exp_amount">Amount ($)</label>
                        <input type="number" id="exp_amount" name="amount" step="0.01" required>
                    </div>
                    <div>
                        <label for="exp_category">Category</label>
                        <input type="text" id="exp_category" name="category" required>
                    </div>
                    <div>
                        <label for="exp_tag">Tag/Sub-category (Optional)</label>
                        <input type="text" id="exp_tag" name="tag">
                    </div>
                    <div>
                        <label for="exp_date">Date</label>
                        <input type="date" id="exp_date" name="date" value="{{ today }}" required>
                    </div>
                </div>
                <button type="submit" class="btn-submit">Log Expense</button>
            </form>
        </div>
        <hr style="border: 0; border-top: 1px solid #ccc; margin: 25px 0;">
    """

def get_income_form_html():
    """Returns the HTML form for adding a new income."""
    return """
        <div class="card">
            <h2>💰 Add New Income</h2>
            <form method="POST" action="{{ url_for('add_record') }}">
                <input type="hidden" name="type" value="income">
                <div class="form-grid">
                    <div>
                        <label for="inc_amount">Amount ($)</label>
                        <input type="number" id="inc_amount" name="amount" step="0.01" required>
                    </div>
                    <div>
                        <label for="inc_source">Source</label>
                        <input type="text" id="inc_source" name="source" required>
                    </div>
                    <div>
                        <label for="inc_date">Date</label>
                        <input type="date" id="inc_date" name="date" value="{{ today }}" required>
                    </div>
                    <div style="grid-column: 4 / 5;"></div>
                </div>
                <button type="submit" class="btn-submit">Log Income</button>
            </form>
        </div>
        <hr style="border: 0; border-top: 1px solid #ccc; margin: 25px 0;">
    """

def get_delete_category_form_html():
    """Returns the HTML form for deleting a whole category."""
    return """
        <div class="card" style="background-color: #fbecec;">
            <h2>⚠️ Delete Category (and Budget)</h2>
            <p style="color: #c82333; font-weight: 600;">WARNING: This will permanently delete ALL expenses and the budget for the selected category.</p>
            <form method="POST" action="{{ delete_url }}">
                <input type="hidden" name="type" value="category">
                <div class="form-grid">
                    <div style="grid-column: 1 / 3;">
                        <label for="del_category_name">Category Name to Delete</label>
                        <input type="text" id="del_category_name" name="category_name" required>
                    </div>
                </div>
                <button type="submit" class="btn-delete" onclick="return confirm('Are you absolutely sure you want to delete ALL records for this category? This cannot be undone.');">
                    Permanently Delete Category
                </button>
            </form>
        </div>
        <hr style="border: 0; border-top: 1px solid #ccc; margin: 25px 0;">
    """

def get_summary_table_html(indexed_expenses, total_spent, delete_url):
    """Generates the HTML table for the expense summary."""
    rows = ""
    for original_index, exp in indexed_expenses:
        tag_display = f" ({exp.tag})" if exp.tag else ""
        rows += f"""
        <tr>
            <td>{exp.date}</td>
            <td>{exp.category}{tag_display}</td>
            <td>${exp.amount:,.2f}</td>
            <td>
                <!-- ACTION now uses the explicit delete_url passed from the route -->
                <form method="POST" action="{delete_url}" style="margin: 0;">
                    <input type="hidden" name="type" value="expense">
                    <input type="hidden" name="expense_index" value="{original_index}">
                    <button type="submit" class="btn-delete" onclick="return confirm('Are you sure you want to remove this single expense?');">
                        Remove
                    </button>
                </form>
            </td>
        </tr>
        """
    
    content = f"""
        <div class="card">
            <h2>📜 Expense Summary (Total: ${total_spent:,.2f})</h2>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Category (Tag)</th>
                        <th>Amount</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                    <tr class="total-row">
                        <td colspan="2">TOTAL SPENT:</td>
                        <td>${total_spent:,.2f}</td>
                        <td></td>
                    </tr>
                </tbody>
            </table>
        </div>
    """
    return content

def get_income_summary_html(indexed_incomes, total_income, delete_url):
    """Generates the HTML table for the income summary, including deletion buttons."""
    rows = ""
    for original_index, inc in indexed_incomes:
        rows += f"""
        <tr>
            <td>{inc.date}</td>
            <td>{inc.source}</td>
            <td class="positive">${inc.amount:,.2f}</td>
            <td>
                <!-- ACTION now uses the explicit delete_url passed from the route -->
                <form method="POST" action="{delete_url}" style="margin: 0;">
                    <input type="hidden" name="type" value="income">
                    <input type="hidden" name="income_index" value="{original_index}">
                    <button type="submit" class="btn-delete" onclick="return confirm('Are you sure you want to remove this income record?');">
                        Remove
                    </button>
                </form>
            </td>
        </tr>
        """
    
    content = f"""
        <div class="card">
            <h2>💰 Income Records (Total: ${total_income:,.2f})</h2>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Source</th>
                        <th>Amount</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                    <tr class="total-row">
                        <td colspan="2">TOTAL INCOME:</td>
                        <td class="positive">${total_income:,.2f}</td>
                        <td></td>
                    </tr>
                </tbody>
            </table>
        </div>
    """
    return content

def get_combined_logs_html(logs):
    """Generates the HTML table for the combined transaction log."""
    rows = ""
    for log in logs:
        # Determine the color and sign based on transaction type
        amount_sign = "" if log['type'] == 'Income' else "-"
        
        rows += f"""
        <tr>
            <td>{log['date']}</td>
            <td><span class="{log['amount_class']}">{log['type']}</span></td>
            <td>{log['description']}</td>
            <td style="text-align: right;" class="{log['amount_class']}">{amount_sign}${log['amount']:,.2f}</td>
        </tr>
        """
    
    content = f"""
        <div class="card">
            <h2>📋 Full Transaction Log (Income & Expenses)</h2>
            <p>All financial transactions sorted by date.</p>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Type</th>
                        <th>Description / Source</th>
                        <th style="text-align: right;">Amount</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
    """
    return content

def get_visualization_html(category_data, trend_data, current_filter):
    """Generates HTML for the visualization page with Chart.js (Pie and Line Charts)."""
    
    category_json = json.dumps(category_data)
    trend_json = json.dumps(trend_data)

    current_filter_map = {
        'all': 'All Time',
        'year': 'Current Year',
        'month': 'Current Month'
    }
    title_suffix = current_filter_map.get(current_filter, 'All Time')
    
    # Generate filter buttons
    filter_buttons = ""
    for filter_id, filter_label in current_filter_map.items():
        active_class = "active" if current_filter == filter_id else ""
        filter_buttons += f"""
        <a href="{url_for('visualization_page', filter=filter_id)}" class="{active_class}">{filter_label}</a>
        """

    content = f"""
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
        
        <div class="filter-btn-group">
            {filter_buttons}
        </div>

        <div class="chart-grid">
            <div class="card">
                <h2>📈 Monthly Spending Trend ({title_suffix})</h2>
                <canvas id="trendLineChart"></canvas>
            </div>
            <div class="card">
                <h2>🥧 Category Spending Breakdown ({title_suffix})</h2>
                <canvas id="categoryPieChart"></canvas>
            </div>
        </div>

        <script>
            // --- PIE CHART DATA ---
            const categoryData = {category_json};

            const ctxPie = document.getElementById('categoryPieChart');

            new Chart(ctxPie, {{
                type: 'pie',
                data: {{
                    labels: categoryData.labels,
                    datasets: [{{
                        label: 'Spending by Category ($)',
                        data: categoryData.data,
                        backgroundColor: [
                            '#004d99', '#0077b6', '#00a896', '#32cd32', 
                            '#ffcc00', '#ff6347', '#9370db', '#87cefa', 
                            '#f08080', '#20b2aa' 
                        ],
                        hoverOffset: 8
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {{
                        legend: {{ position: 'top' }},
                        title: {{ display: true, text: 'Total Expenses by Category' }}
                    }}
                }}
            }});

            // --- LINE CHART DATA ---
            const trendData = {trend_json};
            const ctxLine = document.getElementById('trendLineChart');

            new Chart(ctxLine, {{
                type: 'line',
                data: {{
                    labels: trendData.labels,
                    datasets: [{{
                        label: 'Total Monthly Spending ($)',
                        data: trendData.data,
                        borderColor: '#0077b6',
                        backgroundColor: 'rgba(0, 119, 182, 0.1)',
                        fill: true,
                        tension: 0.4
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: true,
                    scales: {{
                        y: {{ beginAtZero: true, title: {{ display: true, text: 'Amount ($)' }} }}
                    }},
                    plugins: {{
                        title: {{ display: true, text: 'Spending Over Time' }}
                    }}
                }}
            }});
        </script>
    """
    return content

def get_savings_report_html(total_income, total_expense, net_savings):
    """Generates the HTML for the Net Savings Report."""
    
    savings_class = "positive" if net_savings >= 0 else "negative"
    savings_text = "Net Savings" if net_savings >= 0 else "Net Loss"

    content = f"""
        <div class="report-box">
            <h2>Net Financial Status for {datetime.date.today().strftime('%B %Y')}</h2>
            <p><strong>Total Income:</strong> <span class="positive">${total_income:,.2f}</span></p>
            <p><strong>Total Expenses:</strong> <span class="negative">${total_expense:,.2f}</span></p>
            <hr style="margin: 20px auto; width: 50%;">
            <h3>{savings_text}:</h3>
            <p class="amount {savings_class}">${net_savings:,.2f}</p>
        </div>
    """
    return content

def get_budget_form_html():
    """Returns the HTML form for setting/updating a category budget."""
    return """
        <div class="card">
            <h2>🎯 Set/Update Monthly Budget</h2>
            <form method="POST" action="{{ url_for('set_budget') }}">
                <div class="form-grid">
                    <div>
                        <label for="budget_category">Category</label>
                        <input type="text" id="budget_category" name="category" required>
                    </div>
                    <div>
                        <label for="budget_amount">Monthly Limit ($)</label>
                        <input type="number" id="budget_amount" name="amount" step="0.01" required>
                    </div>
                </div>
                <button type="submit" class="btn-submit">Set Budget</button>
            </form>
        </div>
    """

def get_budget_report_html(report_data, delete_url):
    """Generates the HTML table for the Budget Report."""
    rows = ""
    for item in report_data:
        remaining_str = f"${abs(item['remaining']):,.2f}"
        if item['remaining'] < 0:
            remaining_str = f"(${abs(item['remaining']):,.2f})"

        # Action column content logic
        action_content = ""
        if item['category'] in tracker.budgets:
            action_content = f"""
            <form method="POST" action="{delete_url}" style="margin: 0;">
                <input type="hidden" name="type" value="budget">
                <input type="hidden" name="category_name" value="{item['category']}">
                <button type="submit" class="btn-delete" style="padding: 5px 8px;" onclick="return confirm('Are you sure you want to delete the budget limit for {item['category']}?');">
                    Delete Budget
                </button>
            </form>
            """

        rows += f"""
        <tr>
            <td>{item['category']}</td>
            <td>${item['budget']:,.2f}</td>
            <td>${item['spent']:,.2f}</td>
            <td class="{item['status_class']}">{remaining_str}</td>
            <td class="{item['status_class']}">{item['status']}</td>
            <td>{action_content}</td>
        </tr>
        """
    
    content = f"""
        <div class="card">
            <h2>📊 Monthly Budget Report for {datetime.date.today().strftime('%B %Y')}</h2>
            <table class="budget-report">
                <thead>
                    <tr>
                        <th>Category</th>
                        <th>Budget Limit</th>
                        <th>Spent (This Month)</th>
                        <th>Remaining/Over</th>
                        <th>Status</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
    """
    return content

# --- 5. Flask Routes ---

@app.route('/', methods=['GET'])
def index():
    """Home page: Displays forms and the expense summary table."""
    # Note: get_expenses_summary now returns (index, expense) tuples
    indexed_expenses, total_spent = tracker.get_expenses_summary()
    
    # Calculate URLs once and pass them down
    delete_url = url_for('delete_record')
    
    expense_form = render_template_string(get_expense_form_html(), today=datetime.date.today().strftime('%Y-%m-%d'))
    income_form = render_template_string(get_income_form_html(), today=datetime.date.today().strftime('%Y-%m-%d'))
    
    # Pass delete_url to the deletion form and the summary table
    delete_category_form = render_template_string(get_delete_category_form_html(), delete_url=delete_url) # NEW: Passing delete_url
    summary_table = get_summary_table_html(indexed_expenses, total_spent, delete_url=delete_url) # NEW: Passing delete_url
    
    # Concatenate all content blocks
    full_content = expense_form + income_form + delete_category_form + summary_table

    return render_template_string(
        HTML_TEMPLATE, 
        content=full_content, 
        active_tab='summary',
        message=request.args.get('message'),
        success=request.args.get('success') == 'True'
    )

@app.route('/income_management', methods=['GET'])
def income_management():
    """New page: Displays the income summary table with delete options."""
    indexed_incomes, total_income = tracker.get_income_summary()
    delete_url = url_for('delete_record')

    report_content = get_income_summary_html(indexed_incomes, total_income, delete_url)

    return render_template_string(
        HTML_TEMPLATE, 
        content=report_content, 
        active_tab='income_mgmt',
        message=request.args.get('message'),
        success=request.args.get('success') == 'True'
    )

@app.route('/combined_logs', methods=['GET'])
def combined_logs():
    """New page: Displays the combined income and expense transaction logs."""
    logs = tracker.get_combined_logs()

    report_content = get_combined_logs_html(logs)

    return render_template_string(
        HTML_TEMPLATE, 
        content=report_content, 
        active_tab='logs',
        message=request.args.get('message'),
        success=request.args.get('success') == 'True'
    )

@app.route('/visualization', methods=['GET'])
def visualization_page():
    """Visualization page: Displays spending breakdown charts."""
    
    # Get filter from URL, default to 'all'
    time_filter = request.args.get('filter', 'all')
    
    category_data = tracker.get_category_chart_data(time_filter)
    trend_data = tracker.get_monthly_trend_data(time_filter)

    report_content = get_visualization_html(category_data, trend_data, time_filter)

    return render_template_string(
        HTML_TEMPLATE, 
        content=report_content, 
        active_tab='visualization',
        message=request.args.get('message'),
        success=request.args.get('success') == 'True'
    )


@app.route('/net_savings_report', methods=['GET'])
def net_savings_report():
    """Net Savings Report page."""
    total_income, total_expense, net_savings = tracker.calculate_net_savings()

    report_content = get_savings_report_html(total_income, total_expense, net_savings)

    return render_template_string(
        HTML_TEMPLATE, 
        content=report_content, 
        active_tab='savings',
        message=request.args.get('message'),
        success=request.args.get('success') == 'True'
    )

@app.route('/budgeting', methods=['GET'])
def budgeting_page():
    """Budgeting page: Displays form and the budget status report."""
    
    budget_form = render_template_string(get_budget_form_html())
    delete_url = url_for('delete_record')
    report_data = tracker.get_budget_report()
    budget_report = get_budget_report_html(report_data, delete_url) # Pass delete_url
    
    full_content = budget_form + budget_report

    return render_template_string(
        HTML_TEMPLATE, 
        content=full_content, 
        active_tab='budgeting',
        message=request.args.get('message'),
        success=request.args.get('success') == 'True'
    )

@app.route('/set_budget', methods=['POST'])
def set_budget():
    """Handles submission of the Set Budget form."""
    category = request.form.get('category')
    amount = request.form.get('amount', type=float)

    if not category or not category.strip():
        # Redirect to the budgeting page function
        return redirect(url_for('budgeting_page', message="Category cannot be blank.", success='False'))
    
    if amount is None or amount < 0:
        # Redirect to the budgeting page function
        return redirect(url_for('budgeting_page', message="Budget amount must be a non-negative number.", success='False'))

    success, message = tracker.set_budget(category, amount)

    # Redirect to the budgeting page function
    return redirect(url_for('budgeting_page', message=message, success=str(success)))


@app.route('/add_record', methods=['POST'])
def add_record():
    """Handles submission of both Expense and Income forms."""
    record_type = request.form.get('type')
    amount = request.form.get('amount', type=float)
    date_str = request.form.get('date')

    if amount is None or amount <= 0:
        return redirect(url_for('index', message="Amount must be a positive number.", success='False'))

    if record_type == 'expense':
        category = request.form.get('category')
        tag = request.form.get('tag')
        success, message = tracker.add_expense(amount, category, date_str, tag)
    
    elif record_type == 'income':
        source = request.form.get('source')
        success, message = tracker.add_income(amount, source, date_str)
    
    else:
        success = False
        message = "Invalid record type submitted."

    # Redirect back to the home page with a message
    return redirect(url_for('index', message=message, success=str(success)))

@app.route('/delete_record', methods=['POST'])
def delete_record():
    """Handles deletion of a single expense, a single income, or an entire category/budget."""
    record_type = request.form.get('type')
    
    if record_type == 'expense':
        # Delete a single expense by index
        original_index = request.form.get('expense_index', type=int)
        success, message = tracker.remove_expense(original_index)
        redirect_route = 'index'
            
    elif record_type == 'income':
        # Delete a single income by index
        original_index = request.form.get('income_index', type=int)
        success, message = tracker.remove_income(original_index)
        redirect_route = 'income_management'
            
    elif record_type == 'category':
        # Delete all records/budget for a category (Mass Delete)
        category_name = request.form.get('category_name')
        if not category_name:
            success, message = False, "Category name cannot be empty."
        else:
            success, message = tracker.delete_category(category_name)
        redirect_route = 'index'

    elif record_type == 'budget':
        # Delete just the budget limit
        category_name = request.form.get('category_name')
        if not category_name:
            success, message = False, "Category name cannot be empty."
        else:
            success, message = tracker.delete_budget(category_name)
        redirect_route = 'budgeting_page'
    
    else:
        success = False
        message = "Invalid deletion type submitted."
        redirect_route = 'index' # Default fallback

    # Determine the correct page to redirect to based on the deletion type
    return redirect(url_for(redirect_route, message=message, success=str(success)))

# --- 6. Run Application ---

if __name__ == '__main__':
    # Initial data setup check (optional, but good practice)
    if not tracker.expenses and not tracker.incomes:
        tracker.add_expense(750.00, 'Rent', '2025-08-01')
        tracker.add_expense(55.50, 'Food', '2025-08-15', 'Dining Out')
        tracker.add_income(3000.00, 'Salary', datetime.date.today().strftime('%Y-%m-01'))
        tracker.set_budget('Food', 150.00)
        tracker._save()
        print("Sample data added for the web app.")
        
    app.run(debug=True)
