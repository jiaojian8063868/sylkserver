# Copyright (C) 2012 AG Projects. See LICENSE for details
#

from application.notification import NotificationCenter, NotificationData
from twisted.internet import defer
from wokkel.disco import DiscoHandler
from wokkel.muc import UserPresence
from wokkel.xmppim import BasePresenceProtocol, MessageProtocol, PresenceProtocol

from sylk.applications.xmppgateway.datatypes import Identity, FrozenURI
from sylk.applications.xmppgateway.xmpp.stanzas import RECEIPTS_NS, CHATSTATES_NS, ErrorStanza, \
        NormalMessage, MessageReceipt, ChatMessage, ChatComposingIndication,                    \
        AvailabilityPresence, SubscriptionPresence, ProbePresence,                              \
        MUCAvailabilityPresence, GroupChatMessage                                               \

__all__ = ['DiscoProtocol', 'MessageProtocol', 'MUCServerProtocol', 'PresenceProtocol']


class MessageProtocol(MessageProtocol):
    messageTypes = None, 'normal', 'chat', 'headline', 'groupchat', 'error'

    def _onMessage(self, message):
        if message.handled:
            return
        messageType = message.getAttribute("type")
        if messageType not in self.messageTypes:
            message["type"] = 'normal'
        self.onMessage(message)

    def onMessage(self, msg):
        notification_center = NotificationCenter()

        sender_uri = FrozenURI.parse('xmpp:'+msg['from'])
        sender = Identity(sender_uri)
        recipient_uri = FrozenURI.parse('xmpp:'+msg['to'])
        recipient = Identity(recipient_uri)

        msg_type = msg.getAttribute('type')
        msg_id = msg.getAttribute('id', None)
        is_empty = msg.body is None and msg.html is None

        if msg_type == 'error':
            error_type = msg.error['type']
            conditions = [(child.name, child.defaultUri) for child in msg.error.elements()]
            error_message = ErrorStanza('message', sender, recipient, error_type, conditions, id=msg_id)
            notification_center.post_notification('XMPPGotErrorMessage', sender=self.parent, data=NotificationData(error_message=error_message))
            return

        if msg_type in (None, 'normal', 'chat') and not is_empty:
            body = None
            html_body = None
            if msg.html is not None:
                html_body = msg.html.toXml()
            if msg.body is not None:
                body = unicode(msg.body)
            try:
                elem = next(c for c in msg.elements() if c.uri == RECEIPTS_NS)
            except StopIteration:
                use_receipt = False
            else:
                use_receipt = elem.name == u'request'
            if msg_type == 'chat':
                message = ChatMessage(sender, recipient, body, html_body, id=msg_id, use_receipt=use_receipt)
                notification_center.post_notification('XMPPGotChatMessage', sender=self.parent, data=NotificationData(message=message))
            else:
                message = NormalMessage(sender, recipient, body, html_body, id=msg_id, use_receipt=use_receipt)
                notification_center.post_notification('XMPPGotNormalMessage', sender=self.parent, data=NotificationData(message=message))
            return

        # Check if it's a composing indication
        if msg_type == 'chat' and is_empty:
            for elem in msg.elements():
                try:
                    elem = next(c for c in msg.elements() if c.uri == CHATSTATES_NS)
                except StopIteration:
                    pass
                else:
                    composing_indication = ChatComposingIndication(sender, recipient, elem.name, id=msg_id)
                    notification_center.post_notification('XMPPGotComposingIndication', sender=self.parent, data=NotificationData(composing_indication=composing_indication))
                    return

        # Check if it's a receipt acknowledgement
        if is_empty:
            try:
                elem = next(c for c in msg.elements() if c.uri == RECEIPTS_NS)
            except StopIteration:
                pass
            else:
                if elem.name == u'received' and msg_id is not None:
                    receipt = MessageReceipt(sender, recipient, msg_id)
                    notification_center.post_notification('XMPPGotReceipt', sender=self.parent, data=NotificationData(receipt=receipt))


class PresenceProtocol(PresenceProtocol):
    def availableReceived(self, stanza):
        sender_uri = FrozenURI.parse('xmpp:'+stanza.element['from'])
        sender = Identity(sender_uri)
        recipient_uri = FrozenURI.parse('xmpp:'+stanza.element['to'])
        recipient = Identity(recipient_uri)
        id = stanza.element.getAttribute('id')
        show = stanza.show
        statuses = stanza.statuses
        presence_stanza = AvailabilityPresence(sender, recipient, available=True, show=show, statuses=statuses, id=id)
        NotificationCenter().post_notification('XMPPGotPresenceAvailability', sender=self.parent, data=NotificationData(presence_stanza=presence_stanza))

    def unavailableReceived(self, stanza):
        sender_uri = FrozenURI.parse('xmpp:'+stanza.element['from'])
        sender = Identity(sender_uri)
        recipient_uri = FrozenURI.parse('xmpp:'+stanza.element['to'])
        recipient = Identity(recipient_uri)
        id = stanza.element.getAttribute('id')
        presence_stanza = AvailabilityPresence(sender, recipient, available=False, id=id)
        NotificationCenter().post_notification('XMPPGotPresenceAvailability', sender=self.parent, data=NotificationData(presence_stanza=presence_stanza))

    def _process_subscription_stanza(self, stanza):
        sender_uri = FrozenURI.parse('xmpp:'+stanza.element['from'])
        sender = Identity(sender_uri)
        recipient_uri = FrozenURI.parse('xmpp:'+stanza.element['to'])
        recipient = Identity(recipient_uri)
        id = stanza.element.getAttribute('id')
        type = stanza.element.getAttribute('type')
        presence_stanza = SubscriptionPresence(sender, recipient, type, id=id)
        NotificationCenter().post_notification('XMPPGotPresenceSubscriptionStatus', sender=self.parent, data=NotificationData(presence_stanza=presence_stanza))

    def subscribedReceived(self, stanza):
        self._process_subscription_stanza(stanza)

    def unsubscribedReceived(self, stanza):
        self._process_subscription_stanza(stanza)

    def subscribeReceived(self, stanza):
        self._process_subscription_stanza(stanza)

    def unsubscribeReceived(self, stanza):
        self._process_subscription_stanza(stanza)

    def probeReceived(self, stanza):
        sender_uri = FrozenURI.parse('xmpp:'+stanza.element['from'])
        sender = Identity(sender_uri)
        recipient_uri = FrozenURI.parse('xmpp:'+stanza.element['to'])
        recipient = Identity(recipient_uri)
        id = stanza.element.getAttribute('id')
        presence_stanza = ProbePresence(sender, recipient, id=id)
        NotificationCenter().post_notification('XMPPGotPresenceProbe', sender=self.parent, data=NotificationData(presence_stanza=presence_stanza))


class MUCServerProtocol(BasePresenceProtocol):
    messageTypes = None, 'normal', 'chat', 'groupchat'

    presenceTypeParserMap = {'available': UserPresence,
                             'unavailable': UserPresence}

    def connectionInitialized(self):
        BasePresenceProtocol.connectionInitialized(self)
        self.xmlstream.addObserver('/message', self._onMessage)

    def _onMessage(self, message):
        if message.handled:
            return
        messageType = message.getAttribute("type")
        if messageType == 'error':
            return
        if messageType not in self.messageTypes:
            message['type'] = 'normal'
        if messageType == 'groupchat':
            self.onGroupChat(message)
        else:
            # TODO: give error, private messages not supported
            pass

    def onGroupChat(self, msg):
        sender_uri = FrozenURI.parse('xmpp:'+msg['from'])
        sender = Identity(sender_uri)
        recipient_uri = FrozenURI.parse('xmpp:'+msg['to'])
        recipient = Identity(recipient_uri)
        body = None
        html_body = None
        if msg.html is not None:
            html_body = msg.html.toXml()
        if msg.body is not None:
            body = unicode(msg.body)
        message = GroupChatMessage(sender, recipient, body, html_body, id=msg.getAttribute('id', None))
        NotificationCenter().post_notification('XMPPMucGotGroupChat', sender=self.parent, data=NotificationData(message=message))

    def availableReceived(self, stanza):
        sender_uri = FrozenURI.parse('xmpp:'+stanza.element['from'])
        sender = Identity(sender_uri)
        recipient_uri = FrozenURI.parse('xmpp:'+stanza.element['to'])
        recipient = Identity(recipient_uri)
        id = stanza.element.getAttribute('id')
        presence_stanza = MUCAvailabilityPresence(sender, recipient, available=True, id=id)
        NotificationCenter().post_notification('XMPPMucGotPresenceAvailability', sender=self.parent, data=NotificationData(presence_stanza=presence_stanza))

    def unavailableReceived(self, stanza):
        sender_uri = FrozenURI.parse('xmpp:'+stanza.element['from'])
        sender = Identity(sender_uri)
        recipient_uri = FrozenURI.parse('xmpp:'+stanza.element['to'])
        recipient = Identity(recipient_uri)
        id = stanza.element.getAttribute('id')
        presence_stanza = MUCAvailabilityPresence(sender, recipient, available=False, id=id)
        NotificationCenter().post_notification('XMPPMucGotPresenceAvailability', sender=self.parent, data=NotificationData(presence_stanza=presence_stanza))


class DiscoProtocol(DiscoHandler):

    def info(self, requestor, target, nodeIdentifier):
        """
        Gather data for a disco info request.

        @param requestor: The entity that sent the request.
        @type requestor: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @param target: The entity the request was sent to.
        @type target: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @param nodeIdentifier: The optional node being queried, or C{''}.
        @type nodeIdentifier: C{unicode}
        @return: Deferred with the gathered results from sibling handlers.
        @rtype: L{defer.Deferred}
        """

        d = defer.Deferred()

        sender_uri = FrozenURI.parse(requestor)
        sender = Identity(sender_uri)
        target_uri = FrozenURI.parse(target)
        target = Identity(target_uri)

        data = NotificationData(sender=sender, target=target, node_identifier=nodeIdentifier, deferred=d)
        NotificationCenter().post_notification('XMPPGotDiscoInfoRequest', sender=self.parent, data=data)

        return d

    def items(self, requestor, target, nodeIdentifier):
        """
        Gather data for a disco items request.

        @param requestor: The entity that sent the request.
        @type requestor: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @param target: The entity the request was sent to.
        @type target: L{JID<twisted.words.protocols.jabber.jid.JID>}
        @param nodeIdentifier: The optional node being queried, or C{''}.
        @type nodeIdentifier: C{unicode}
        @return: Deferred with the gathered results from sibling handlers.
        @rtype: L{defer.Deferred}
        """

        d = defer.Deferred()

        sender_uri = FrozenURI.parse(requestor)
        sender = Identity(sender_uri)
        target_uri = FrozenURI.parse(target)
        target = Identity(target_uri)

        data = NotificationData(sender=sender, target=target, node_identifier=nodeIdentifier, deferred=d)
        NotificationCenter().post_notification('XMPPGotDiscoItemsRequest', sender=self.parent, data=data)

        return d

