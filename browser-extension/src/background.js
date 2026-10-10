// activeTab is granted by the toolbar action or its user-invoked keyboard command.
// Badge updates are ordered so a close cannot be overwritten by an older active message.
const badgeQueues = new Map();
function badge(tabId, text) {
  const previous = badgeQueues.get(tabId) || Promise.resolve();
  const pending = previous.catch(() => {}).then(() => chrome.action.setBadgeText({ tabId, text }));
  badgeQueues.set(tabId, pending);
  pending.finally(() => { if (badgeQueues.get(tabId) === pending) badgeQueues.delete(tabId); }).catch(() => {});
  return pending;
}
chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id) return;
  try {
    // Repeated activation replaces our own stylesheet instead of accumulating copies.
    await chrome.scripting.removeCSS({ target: { tabId: tab.id }, files: ['dock.css'] });
    await chrome.scripting.insertCSS({ target: { tabId: tab.id }, files: ['dock.css'] });
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'], world: 'ISOLATED' });
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['reader.js'], world: 'MAIN' });
    // A live content script announces successful reader activation. No unconditional ON here:
    // the user can close the panel while the asynchronous injections are still in progress.
  } catch (error) {
    await badge(tab.id, '!');
    await chrome.action.setTitle({ tabId: tab.id, title: 'Cannot enable here. Open the Dify workflow page and click again.' });
    console.warn('DMN preview activation failed:', error?.message || 'Unknown error');
  }
});
chrome.runtime.onMessage.addListener((message, sender) => {
  const tabId = sender.tab?.id;
  if (!tabId) return;
  if (message?.type === 'dmn-preview-active') {
    badge(tabId, 'ON').catch(() => {});
    chrome.action.setBadgeBackgroundColor({ tabId, color: '#155e75' });
    chrome.action.setTitle({ tabId, title: 'DMN preview enabled for this page; close in the preview panel' });
  }
  if (message?.type === 'dmn-preview-closed') {
    badge(tabId, '').catch(() => {});
    chrome.action.setTitle({ tabId, title: 'Enable DMN matrix on this tab' });
    chrome.scripting.removeCSS({ target: { tabId }, files: ['dock.css'] }).catch(() => {});
  }
});

// Basic loading notifications do not require the broad tabs permission.
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === 'loading') {
    badge(tabId, '').catch(() => {});
    chrome.action.setTitle({ tabId, title: 'Enable DMN matrix on this tab' });
  }
});
