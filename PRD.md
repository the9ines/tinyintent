<!DOCTYPE html>
<html>
    <head>
        <title>Context &ndash; share whatever you see with others in seconds</title>
        <link rel="shortcut icon" href="/favicon.png">
        <style type="text/css">
			/* Reset */
			html, body, div, span, applet, object, iframe,
			h1, h2, h3, h4, h5, h6, p, blockquote, pre,
			a, abbr, acronym, address, big, cite, code,
			del, dfn, em, font, img, ins, kbd, q, s, samp,
			small, strike, strong, sub, sup, tt, var,
			b, u, i, center,
			dl, dt, dd, ol, ul, li,
			fieldset, form, label, legend,
			table, caption, tbody, tfoot, thead, tr, th, td {
				margin: 0;
				padding: 0;
				border: 0;
				outline: 0;
				font-size: 100%;
				vertical-align: baseline;
			}
            .context_spacer { height: 30px; width: 100%; }
            .context_footer { 
                color: #777; width: 100%; position: fixed; left: 0px; bottom: 0px; margin: 10px 0px 0px 0px; padding: 10px; border-top: solid 1px #ccc; background: white;
				line-height: 16px; font-weight: 400; font-family: 'Montserrat', sans-serif; font-size: 16px; z-index: 1000; box-sizing: initial;
                -webkit-font-smoothing: antialiased !important; -moz-osx-font-smoothing: grayscale !important; text-rendering: optimizeLegibility !important;
            }
            .context_footer .context_logo { height: 16px; width: 16px; margin: -2px 3px 0px 2px; vertical-align: middle; display: inline; }
            .context_footer a.context_logo_link { font-weight: 400; }
            .context_footer a.context_link { font-weight: 400; }
			#report-link { margin-left: 10px; }
            .context_footer a:link, .context_footer a:visited { text-decoration: none; color: #555; border: 0px; font-weight: 400; }
            .context_footer a:hover { cursor: pointer; text-decoration: none; color: #777; }
            .context_footer .context_report { float: right; margin-right: 20px; }
            @media screen and (max-width: 1020px) {
                html { font-size: 160%; }
                .context_spacer { height: 100px; }
                .context_footer { font-size: 1.4rem; line-height: 1.8rem; margin: 10px; padding: 10px; }
                .context_footer .context_logo { height: 32px; width: 32px; }
                .context_footer a.context_logo_link { padding: 0px; margin: 0px; }
                .context_footer a.context_link { padding: 10px; margin: 10px; }
                .context_footer .context_report { height: auto; float: none; display: inline; } 
                .nowrap { white-space: nowrap; }
                .context_message { font-size: 2rem; }
            }
        </style>
        <meta name="referrer" content="no-referrer" />
        <script type="text/javascript" nonce="27871e80a1014278b5c51559b8c7e459">
			(function(i,s,o,g,r,a,m){i['GoogleAnalyticsObject']=r;i[r]=i[r]||function(){
			(i[r].q=i[r].q||[]).push(arguments)},i[r].l=1*new Date();a=s.createElement(o),
			m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)
			})(window,document,'script','https://www.google-analytics.com/analytics.js','ga');

			ga('create', 'UA-93094602-1', 'auto');
			ga('send', 'pageview');
			ga('send', 'event', 'All', 'content');

            document.addEventListener("DOMContentLoaded", function(event) {
                var reportLink = document.getElementById('report-link');
                reportLink.onclick = function() {
                    var request = new XMLHttpRequest();
                    request.open('POST', '/report', true);
                    request.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
                    var url = encodeURIComponent(window.document.location);
                    request.send(encodeURI('url=' + url + '&key=AAD4RJQ6Eg&v=2'));
                    reportLink.innerText = 'Thanks for reporting';
                    reportLink.disabled = true;
                    reportLink.onclick = null;
                };
            });
		</script>
    </head>
    <body>
        
        <div class="context_message" style="padding: 20px;">Paste expired or not found. Create your own Context <a href="/">here</a>.</div>
        
        <div class="context_spacer">
            <img height="1" width="1" style="display:none" src="https://www.quora.com/_/ad/f88319ba83cb2e40064aff2dfeaab96e/pixel" />
			<script type="text/javascript" nonce="27871e80a1014278b5c51559b8c7e459">
				/* <![CDATA[ */
				var google_conversion_id = 856256774;
				var google_conversion_language = "en";
				var google_conversion_format = "3";
				var google_conversion_color = "ffffff";
				var google_conversion_label = "USE8CMaloXAQhuKlmAM";
				var google_remarketing_only = false;
				/* ]]> */
			</script>
			<script type="text/javascript" src="//www.googleadservices.com/pagead/conversion.js"></script>
			<noscript>
				<div style="display:inline;">
				<img height="1" width="1" style="border-style:none;" alt="" src="//www.googleadservices.com/pagead/conversion/856256774/?label=USE8CMaloXAQhuKlmAM&amp;guid=ON&amp;script=0"/>
				</div>
			</noscript>
        </div>
        <div class="context_footer">
        
            Share whatever you see with others in seconds with 
            <a class="context_logo_link nowrap" href="/"><img src="/favicon.png" class="context_logo" />Context</a>.
        
        </div>
    </body>
</html>