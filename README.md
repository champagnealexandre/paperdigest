- Source feeds: right now we’re supporting keywords-ool, keywords-astrobiology and ool-ressources
- We’re not using any 'doi hunter' — some articles aren’t being parsed correctly and are skipped entirely
- We’re running the script every hour

**testing workflow**
- delete history
- cancel deploy started right after committing
- unfollow feed then follow again adding `?v=XXX`
