[How to: Contribute code](https://github.com/SickGear/SickGear/wiki/%5BHow-to%5D-Contribute-Code?ref_style=button)
  
## Create an issue report

> [!NOTE]
> Guessing what is and isn't important in a report wastes time and ruins a smooth resolution.

1. State branch and current commit hash from the "About" page  
   Can't reach the about page? Run `git rev-parse @{1}` at a cmdline in the SG install directory, and send the output.  
2. Explain what you expect to see **and** what you actually see (less than 250 chars for each)  
3. Reproduce the issue again yourself and clearly **write the steps** taken  
   Include relevant logs (see footnote and image [^1]), screenshots, and config information  
4. Add Python version and OS under the "`Additional notes`" section, along with anything else useful to know  
  
> [!IMPORTANT]
> * *Provide clear detail to allow us to quickly reproduce the issue to focus on a fix*  
> * Also, you can use your written steps to verify the fix
  
[^1]: Logs *must* be created by setting "File logging level" to "Debug and the next 3 levels" at General Config
**before** you reproduce the issue again yourself at step 3 above. <img src="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/screenies/config-log-level-debug.png">

> [!TIP]
> :+1: Do wrap log lines in "`<pre>`" tags for better readability. E.g. `<pre>insert log text here</pre>`  
> :-1: Don't write an essay. Long reports take longer to answer due to a human reaction that is [TL;DR](https://en.wiktionary.org/wiki/TL;DR)  
> :+1: Do use the [GitHub Gists](https://gist.github.com/) feature instead of Pastebin, but if you must use PB then...  
<img src="https://raw.githubusercontent.com/wiki/SickGear/SickGear/images/prefer-gists.png">  

