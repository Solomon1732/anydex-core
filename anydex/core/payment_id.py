
class PaymentId:
    """Used for having a validated instance of a payment id that we can monitor."""

    def __init__(self, payment_id: str):
        """
        :param payment_id: String representation of the id of the payment
        :type payment_id: str
        :raises TypeError: Thrown when the type of payment_id is invalid
        """
        if not isinstance(payment_id, str):
            raise TypeError("Payment id must be a string")

        self._payment_id = payment_id

    @property
    def payment_id(self):
        """
        Return the payment id.
        """
        return self._payment_id

    def __str__(self):
        return self._payment_id

    def __eq__(self, other):
        if not isinstance(other, PaymentId):
            return NotImplemented
        return self._payment_id == other.payment_id

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self._payment_id)
