import logging,re
class RedactResetLinks(logging.Filter):
    def filter(self,record):
        text=record.getMessage()
        record.msg=re.sub(r'/reset/[^/\s]+/[^/\s]+/', '/reset/[redacted]/',text)
        record.args=()
        return True
