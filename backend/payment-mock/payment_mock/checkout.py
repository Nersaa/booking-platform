"""The hosted checkout page, the one part of the provider a guest sees.

It works in test mode only: payments succeed or fail by the test card number, and other
card numbers are refused, so nobody types a real card into a demo.
"""

from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from payment_mock.main import Payment

# Test card numbers, like the ones real providers publish for their sandboxes.
TEST_CARDS = {
    "4242424242424242": "succeeded",
    "4000000000000002": "failed",
}


def render(payment: "Payment", error: str | None = None) -> str:
    amount = f"{payment.amount / 100:,.2f} {payment.currency}"
    back = (
        f'<a class="back" href="{escape(payment.return_url)}">Back to the shop</a>'
        if payment.return_url
        else ""
    )

    if payment.status == "succeeded":
        body = f'<p class="result ok">Payment of {amount} succeeded.</p>{back}'
    elif payment.status == "failed":
        body = (
            '<p class="result fail">Your card was declined. No money was taken.</p>'
            f"<p>Go back and start the payment again with another card.</p>{back}"
        )
    else:
        alert = f'<p class="result fail" role="alert">{escape(error)}</p>' if error else ""
        body = f"""
        {alert}
        <form method="post" action="/checkout/{escape(payment.id)}">
          <label>Card number
            <input name="card_number" inputmode="numeric" autocomplete="off"
                   value="4242 4242 4242 4242" required>
          </label>
          <div class="row">
            <label>Expiry <input value="12 / 34" autocomplete="off"></label>
            <label>CVC <input value="123" autocomplete="off"></label>
          </div>
          <button>Pay {amount}</button>
        </form>
        <div class="cards">
          <p>Test cards</p>
          <p><code>4242 4242 4242 4242</code> pays</p>
          <p><code>4000 0000 0000 0002</code> is declined</p>
        </div>
        {back.replace("Back to the shop", "Cancel and go back")}"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pay {amount}</title>
<style>{STYLE}</style>
</head>
<body>
<main>
  <header><strong>Test payments</strong><span class="badge">Test mode</span></header>
  <p class="description">{escape(payment.description) or "Payment"}</p>
  <p class="amount">{amount}</p>
  {body}
</main>
</body>
</html>"""


STYLE = """
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center;
  background: #eef0f6; color: #1f2333; font: 16px/1.5 system-ui, sans-serif; }
main { width: min(26rem, 100% - 2rem); margin: 2rem 0; padding: 1.75rem;
  border-radius: 16px; background: #fff; box-shadow: 0 8px 30px rgb(31 35 51 / 12%); }
header { display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 1.25rem; color: #4b4fd6; }
.badge { padding: 0.125rem 0.5rem; border-radius: 6px; background: #fff3cd; color: #7a5800;
  font-size: 0.75rem; font-weight: 700; }
.description { margin: 0; color: #5d6275; }
.amount { margin: 0 0 1.25rem; font-size: 2rem; font-weight: 700; }
form { display: grid; gap: 0.875rem; }
label { display: grid; gap: 0.25rem; font-size: 0.875rem; font-weight: 600; }
input { width: 100%; min-width: 0; height: 2.75rem; padding: 0 0.75rem;
  border: 1px solid #c9ccd8; border-radius: 8px; font: inherit; letter-spacing: 0.04em; }
input:focus { outline: 2px solid #4b4fd6; outline-offset: 1px; }
.row { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
button { height: 3rem; border: 0; border-radius: 8px; background: #4b4fd6; color: #fff;
  font: inherit; font-weight: 700; cursor: pointer; }
button:hover { background: #3a3eb8; }
.cards { margin-top: 1.25rem; padding: 0.75rem 1rem; border-radius: 8px; background: #f5f6fa;
  font-size: 0.875rem; }
.cards p { margin: 0.125rem 0; }
.cards p:first-child { font-weight: 700; }
.result { padding: 0.75rem 1rem; border-radius: 8px; font-weight: 600; }
.ok { background: #e3f5ea; color: #1d6b3b; }
.fail { background: #fdecea; color: #a1281b; }
.back { display: inline-block; margin-top: 1rem; color: #4b4fd6; }
"""
