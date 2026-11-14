class DrChronoAuthError(Exception):
    """DrChrono sign-in or token refresh failed; the user must sign in again."""

    @property
    def message(self):  # read by search.views
        return str(self)
