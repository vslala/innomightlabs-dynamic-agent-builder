=== Innomight AI Search ===
Contributors: vslala
Tags: ai, search, chatbot, assistant, chat
Requires at least: 6.3
Tested up to: 7.1
Requires PHP: 7.4
Stable tag: 1.0.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Add an AI follow-up chat to your search results. Visitors search as usual, then ask questions that your Innomight Labs agent answers live.

== Description ==

Innomight AI Search turns your site's search results into a conversation. Visitors search as they always have and see your normal results first. A chat box lets them ask follow-up questions, and the answer streams in word by word.

The assistant is your own agent on [Innomight Labs](https://innomightlabs.com/). The agent does the searching and answering; WordPress sends only the visitor's question, so no post content is copied to a third party by this plugin.

**Features**

* Follow-up chat on search results, placed automatically above or below the results. Works with block themes and classic themes.
* Live streaming answers, with readable formatting (paragraphs, lists, links, code).
* A block and a `[innomight_ai_search]` shortcode to place the chat anywhere.
* Conversations remember earlier questions for the visit.
* Looks like your theme: colours and fonts follow it, with an optional accent colour.
* Your agent's secret key stays on your server and is never sent to visitors.
* Hourly limits per visitor address and per site to protect your AI allowance.
* Editable title, intro, starter questions and instructions.

**Requires** a free or paid [Innomight Labs account](https://innomightlabs.com/pricing) (there is a free plan) and an agent. Give the agent a way to search your site (for example a tool or knowledge base), and create a secret key (`sk_live_…`) for it.

== External services ==

This plugin connects to the Innomight Labs service to answer visitors' questions. It does nothing until an administrator enters an agent ID and secret key and switches the chat on.

* **What it is:** Innomight Labs API at `https://api.innomightlabs.com` (a different backend URL can be set for testing).
* **When data is sent:** when a visitor asks a question in the chat, and when an administrator clicks "Test connection".
* **What is sent:** the visitor's question; a random identifier generated in the visitor's browser (so each visitor has their own conversation); the search term that led to the chat; your site name and URL (in the agent's conversation instructions); and your agent's secret key, which authenticates the request from your server. The visitor's IP address is used only on your server for the hourly limits and is not sent.
* **What is stored:** Innomight Labs keeps the conversation (questions and answers) with the agent, and its model provider processes it.
* Service terms: https://innomightlabs.com/legal/terms
* Privacy policy: https://innomightlabs.com/legal/privacy

Because questions are processed by a third party, mention this in your site's privacy policy. The agent you connect is available to every visitor: anything it can remember or do is reachable through the chat, so use an agent intended for public questions.

== See it in action ==

[Watch the captioned walkthrough](https://innomightlabs.com/downloads/plugins/wordpress-ai-search) or [open the video](https://innomightlabs.com/plugins/wordpress-ai-search/demo.mp4).

Recorded with Playwright on a real WordPress site: search for memory, ask the agent to find LLM posts, narrow the results with a follow-up question, then open the linked article. The answers are live, not mocked. This silent, 54-second recording includes English action captions in the plugin page's video player.

![Normal WordPress search results with the AI follow-up chat above them](https://innomightlabs.com/plugins/wordpress-ai-search/screenshot-4.png)

![The agent finds relevant LLM posts and returns links](https://innomightlabs.com/plugins/wordpress-ai-search/screenshot-5.png)

![A follow-up question identifies the context-memory article and its publication date](https://innomightlabs.com/plugins/wordpress-ai-search/screenshot-6.png)

A second recording, on the BeMyAficionado blog, searches for Microservices and asks in which order to read all the matching posts. It then asks for a summary of one article and for newer posts on the wider topic. The answers are live, not mocked. The recording is silent, about two and a half minutes long and has English action captions. [Watch it on the plugin page](https://innomightlabs.com/downloads/plugins/wordpress-ai-search) or [open the video](https://innomightlabs.com/plugins/wordpress-ai-search/demo-microservices.mp4).

![Searching Microservices lists every matching article, with the AI chat above](https://innomightlabs.com/plugins/wordpress-ai-search/screenshot-7.png)

![The agent suggests an order to read all the matching posts](https://innomightlabs.com/plugins/wordpress-ai-search/screenshot-8.png)

![The agent summarises one article from its full text](https://innomightlabs.com/plugins/wordpress-ai-search/screenshot-9.png)

The connected agent determines what the chat can answer. The first demo agent can search post titles and metadata. The second also has a tool that reads a post's full content (the Innomight WordPress Search skill's read_post action), which is what lets it summarise an article; without such a tool or a knowledge base, summaries aren't available.

== Installation ==

1. Upload the plugin or install it from the Plugins screen, then activate it.
2. Go to **Settings → Innomight AI Search**.
3. Enter your **Agent ID** and **Agent secret key**, tick **Let visitors chat with my agent**, and save.
4. Click **Test connection**, then search your site and ask a question.

You can also define `INNOMIGHT_SEARCH_SECRET_KEY` (environment variable or `wp-config.php` constant) instead of saving the key in the database.

== Frequently Asked Questions ==

= Do I need an Innomight Labs account? =

Yes. Sign up at https://innomightlabs.com/pricing (a free plan is available), create an agent, and create a secret key for it.

= Where do I get help? =

Use the contact form at https://innomightlabs.com/contact, or the plugin's support forum on WordPress.org.

= Does it change my normal search results? =

No. Results are unchanged; the chat is added next to them.

= Why is the answer not word by word on my site? =

Streaming needs PHP's cURL extension and a server that does not buffer responses. Without cURL the full answer appears at once. If a proxy or cache buffers responses, exclude `/wp-json/innomight-search/v1/chat` from buffering.

= Where does the agent get my articles from? =

From its own tools or knowledge base. This plugin does not send post content.

= Can visitors misuse it? =

Questions are limited to 40 per visitor address and 400 per site each hour (change with the `innomight_search_limits` filter). Use an agent meant for the public and keep its permissions narrow.

= Can I place the chat on other pages? =

Yes. Use the "Innomight AI Search" block or the `[innomight_ai_search]` shortcode, and set automatic placement to "off" if you only want manual placement.

= Does uninstalling remove my settings? =

Yes. Deleting the plugin removes its settings and counters.

== Screenshots ==

1. The follow-up chat on search results in a block theme (Twenty Twenty-Five). The normal results stay below.
2. The same chat styled by a custom theme: colours and fonts follow the site.
3. Settings: agent, secret key, instructions, placement and wording.
4. Live preview: normal search results and the AI follow-up chat on Varun Shrivastava's blog.
5. Live preview: the agent finds LLM posts and returns links.
6. Live preview: a contextual follow-up selects an article and its publication date.
7. Live site: searching "Microservices" lists every matching article, with the follow-up chat above.
8. Live site: the agent suggests the order in which to read all the matching posts.
9. Live site: the agent summarises one article from its full text.

== Changelog ==

= 1.0.0 =
* First release.

== Upgrade Notice ==

= 1.0.0 =
First release.
