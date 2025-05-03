# Retrieving district information from representatives where info doesn't exist in public datasets


Feel free to access our postgres database. URI: `postgresql://postgres:postgres@localhost:5432/gov"`
1. Check if not exists in public db (already ingressed)

We'll do this with:

`select count(*) from district_offices where bioguide_id = 's001150';`  IF count=0, district contact info not exists


    - We can source this bioguide from table `members_contact` which should exist for most reps. 

        -`select bioguideid from members_contact;` 

2. We will visit the contact page from that bioguide's `contact_page` column in table `members_contact`. This will give us the URL. 

3. We will go to the URL, extract all HTML. 

4. That HTML will then be used to extract all contact information boxes. Common conventions for district info in the pages being:

- more than 1 'box' which contains district contact information. 
- having the district info in the footer (so near bottom of the page/html). 

We will be using the Anthropic LLM SDK to scrape this data as it's largely free form. Provided are some examples to give you a better idea of the type of information we'll be scraping. These may be useful to you as the programmer either for formulating the prompt or even passing them along as examples in the system prompt.  

## Here's some examples of contact info and their source. 

### https://mcdowell.house.gov/contact
```html
<div class="evo-footer-right">
                                      
  <div class="views-element-container block block--evo-drupaltheme-71-views-block--evo-office-locations-block-list">

  
            <h2>Office Locations</h2>
        

      <div block="evo_drupaltheme_71_views_block__evo_office_locations_block_list"><div class="office-locations js-view-dom-id-8c68177e0bfd5e956cf34d3fc543f5023320e29de1bce196473934497bbc1291">
  
  
  

  
  
  

  <div class="evo-view-evo-office-locations evo-view-wrapper">
  <div class="evo-views-row-container">
          <div class="views-row evo-views-row views-row-0 views-row-first"><div class="views-field views-field-title"><span class="field-content"><a href="/contact/offices/washington-dc-office" hreflang="en">Washington DC Office</a></span></div><div class="views-field views-field-field-evo-address-address-line1"><span class="field-content">1032 Longworth House Office Building</span></div><span><span>Washington, </span></span><span>DC&nbsp;&nbsp;</span><span class="views-field views-field-field-evo-address-postal-code"><span class="field-content">20515</span></span><div class="views-field views-field-field-evo-phone"><span class="views-label views-label-field-evo-phone">Phone: </span><span class="field-content">(202) 225-3065</span></div></div>
          <div class="views-row evo-views-row views-row-1 views-row-last"><div class="views-field views-field-title"><span class="field-content"><a href="/contact/offices/district-office-3" hreflang="en">District Office</a></span></div><div class="views-field views-field-field-evo-address-address-line1"><span class="field-content">30 E. 1st Ave</span></div><span><span>Lexington, </span></span><span>NC&nbsp;&nbsp;</span><span class="views-field views-field-field-evo-address-postal-code"><span class="field-content">27292</span></span><div class="views-field views-field-field-evo-phone"><span class="views-label views-label-field-evo-phone">Phone: </span><span class="field-content">(336) 333-5005</span></div></div>
    </div>
</div>

    

  
  

  
  
</div>
</div>

  
  </div>


                                </div>
```

### https://www.schiff.senate.gov/contact/
```html
<div data-particle_enable="false" data-particle-mobile-disabled="false" class="elementor-element elementor-element-1b44729 e-con-full e-flex e-con e-child" data-id="1b44729" data-element_type="container" data-settings="{&quot;background_background&quot;:&quot;classic&quot;}">
		<div data-particle_enable="false" data-particle-mobile-disabled="false" class="elementor-element elementor-element-f1399aa e-con-full e-flex e-con e-child" data-id="f1399aa" data-element_type="container">
				<div class="elementor-element elementor-element-7c7c55e elementor-widget elementor-widget-heading" data-id="7c7c55e" data-element_type="widget" data-widget_type="heading.default">
				<div class="elementor-widget-container">
					<h2 class="elementor-heading-title elementor-size-default">Office Locations</h2>				</div>
				</div>
				<div class="elementor-element elementor-element-d3c66ac elementor-widget elementor-widget-text-editor" data-id="d3c66ac" data-element_type="widget" data-widget_type="text-editor.default">
				<div class="elementor-widget-container">
									<p>Please call for an appointment to be sure a<br>staff member will be available to speak with you.</p>								</div>
				</div>
				</div>
		<div data-particle_enable="false" data-particle-mobile-disabled="false" class="elementor-element elementor-element-25e47e1 e-con-full js-LocationsContent e-flex e-con e-child" data-id="25e47e1" data-element_type="container" data-settings="{&quot;background_background&quot;:&quot;classic&quot;}">
		<div data-particle_enable="false" data-particle-mobile-disabled="false" class="elementor-element elementor-element-a0b9d1f e-grid e-con-full e-con e-child" data-id="a0b9d1f" data-element_type="container">
		<div data-particle_enable="false" data-particle-mobile-disabled="false" class="elementor-element elementor-element-92db585 Location e-con-full e-flex e-con e-child" data-id="92db585" data-element_type="container" data-location="map-sanfrancisco">
				<div class="elementor-element elementor-element-a427278 OfficeLocation__heading elementor-widget elementor-widget-heading" data-id="a427278" data-element_type="widget" data-widget_type="heading.default">
				<div class="elementor-widget-container">
					<h3 class="elementor-heading-title elementor-size-default" style="color: rgb(9, 101, 220);">San Francisco</h3>				</div>
				</div>
				<div class="elementor-element elementor-element-e9df23b LocationsText elementor-widget elementor-widget-text-editor" data-id="e9df23b" data-element_type="widget" data-widget_type="text-editor.default">
				<div class="elementor-widget-container">
									<p>1 Post St,<br>Suite 2450<br>San Francisco, CA 94104</p>								</div>
				</div>
				<div class="elementor-element elementor-element-f84f176 elementor-icon-list--layout-traditional elementor-list-item-link-full_width elementor-widget elementor-widget-icon-list" data-id="f84f176" data-element_type="widget" data-widget_type="icon-list.default">
				<div class="elementor-widget-container">
							<ul class="elementor-icon-list-items">
							<li class="elementor-icon-list-item">
											<a href="tel:4153930707">

												<span class="elementor-icon-list-icon">
							<i aria-hidden="true" class="fas fa-phone-alt"></i>						</span>
										<span class="elementor-icon-list-text">(415) 393-0707</span>
											</a>
									</li>
						</ul>
						</div>
				</div>
				<div class="elementor-element elementor-element-438fa4a ButtonWrapper--location elementor-widget elementor-widget-button" data-id="438fa4a" data-element_type="widget" data-widget_type="button.default">
				<div class="elementor-widget-container">
									<div class="elementor-button-wrapper">
					<a class="elementor-button elementor-button-link elementor-size-sm" href="https://www.google.com/maps/place/1+Post+St+%232450,+San+Francisco,+CA+94104/@37.7887748,-122.4026656,17z/data=!3m1!4b1!4m6!3m5!1s0x80858088365f3a4b:0xaf2ece841da24c84!8m2!3d37.7887748!4d-122.4026656!16s%2Fg%2F11lkj5hd9y?entry=ttu&amp;g_ep=EgoyMDI1MDIyNS4wIKXMDSoASAFQAw%3D%3D" target="_blank">
						<span class="elementor-button-content-wrapper">
						<span class="elementor-button-icon">
				<i aria-hidden="true" class="fas fa-long-arrow-alt-right"></i>			</span>
									<span class="elementor-button-text">Directions</span>
					</span>
					</a>
				</div>
								</div>
				</div>
				</div>
		<div data-particle_enable="false" data-particle-mobile-disabled="false" class="elementor-element elementor-element-450e3be Location e-con-full e-flex e-con e-child" data-id="450e3be" data-element_type="container" data-location="map-fresno">
				<div class="elementor-element elementor-element-4563251 OfficeLocation__heading elementor-widget elementor-widget-heading" data-id="4563251" data-element_type="widget" data-widget_type="heading.default">
				<div class="elementor-widget-container">
					<h3 class="elementor-heading-title elementor-size-default" style="color: rgb(21, 29, 61);">Fresno</h3>				</div>
				</div>
				<div class="elementor-element elementor-element-b955957 LocationsText elementor-widget elementor-widget-text-editor" data-id="b955957" data-element_type="widget" data-widget_type="text-editor.default">
				<div class="elementor-widget-container">
									<p>2500 Tulare Street<br>Suite 4290<br>Fresno, CA 93721</p>								</div>
				</div>
				<div class="elementor-element elementor-element-0ee1d9e elementor-icon-list--layout-traditional elementor-list-item-link-full_width elementor-widget elementor-widget-icon-list" data-id="0ee1d9e" data-element_type="widget" data-widget_type="icon-list.default">
				<div class="elementor-widget-container">
							<ul class="elementor-icon-list-items">
							<li class="elementor-icon-list-item">
											<a href="tel:5594857430">

												<span class="elementor-icon-list-icon">
							<i aria-hidden="true" class="fas fa-phone-alt"></i>						</span>
										<span class="elementor-icon-list-text">(559) 485-7430</span>
											</a>
									</li>
						</ul>
						</div>
				</div>
				<div class="elementor-element elementor-element-4bf863f ButtonWrapper--location elementor-widget elementor-widget-button" data-id="4bf863f" data-element_type="widget" data-widget_type="button.default">
				<div class="elementor-widget-container">
									<div class="elementor-button-wrapper">
					<a class="elementor-button elementor-button-link elementor-size-sm" href="https://www.google.com/maps/place/Robert+E.+Coyle+United+States+Courthouse,+2500+Tulare+St+%23+4290,+Fresno,+CA+93721/data=!4m2!3m1!1s0x80945e21fc5fc43f:0x23db2d4546f0de2?sa=X&amp;ved=1t:242&amp;ictx=111" target="_blank">
						<span class="elementor-button-content-wrapper">
						<span class="elementor-button-icon">
				<i aria-hidden="true" class="fas fa-long-arrow-alt-right"></i>			</span>
									<span class="elementor-button-text">Directions</span>
					</span>
					</a>
				</div>
								</div>
				</div>
				</div>
		<div data-particle_enable="false" data-particle-mobile-disabled="false" class="elementor-element elementor-element-2b19edd Location e-con-full e-flex e-con e-child" data-id="2b19edd" data-element_type="container" data-location="map-sandiego">
				<div class="elementor-element elementor-element-e123592 OfficeLocation__heading elementor-widget elementor-widget-heading" data-id="e123592" data-element_type="widget" data-widget_type="heading.default">
				<div class="elementor-widget-container">
					<h3 class="elementor-heading-title elementor-size-default" style="color: rgb(21, 29, 61);">San Diego</h3>				</div>
				</div>
				<div class="elementor-element elementor-element-5e29332 LocationsText elementor-widget elementor-widget-text-editor" data-id="5e29332" data-element_type="widget" data-widget_type="text-editor.default">
				<div class="elementor-widget-container">
									<p>880 Front Street<br>Suite 4236<br>San Diego, CA 92101</p>								</div>
				</div>
				<div class="elementor-element elementor-element-e08d0eb elementor-icon-list--layout-traditional elementor-list-item-link-full_width elementor-widget elementor-widget-icon-list" data-id="e08d0eb" data-element_type="widget" data-widget_type="icon-list.default">
				<div class="elementor-widget-container">
							<ul class="elementor-icon-list-items">
							<li class="elementor-icon-list-item">
											<a href="tel:6192319712">

												<span class="elementor-icon-list-icon">
							<i aria-hidden="true" class="fas fa-phone-alt"></i>						</span>
										<span class="elementor-icon-list-text">(619) 231-9712</span>
											</a>
									</li>
						</ul>
						</div>
				</div>
				<div class="elementor-element elementor-element-634fa5b ButtonWrapper--location elementor-widget elementor-widget-button" data-id="634fa5b" data-element_type="widget" data-widget_type="button.default">
				<div class="elementor-widget-container">
									<div class="elementor-button-wrapper">
					<a class="elementor-button elementor-button-link elementor-size-sm" href="https://maps.app.goo.gl/LsCP8zuVX8kMRgjL6" target="_blank">
						<span class="elementor-button-content-wrapper">
						<span class="elementor-button-icon">
				<i aria-hidden="true" class="fas fa-long-arrow-alt-right"></i>			</span>
									<span class="elementor-button-text">Directions</span>
					</span>
					</a>
				</div>
								</div>
				</div>
				</div>
		<div data-particle_enable="false" data-particle-mobile-disabled="false" class="elementor-element elementor-element-9e2d384 Location e-con-full e-flex e-con e-child" data-id="9e2d384" data-element_type="container" data-location="map-downtownla">
				<div class="elementor-element elementor-element-0ecddda OfficeLocation__heading elementor-widget elementor-widget-heading" data-id="0ecddda" data-element_type="widget" data-widget_type="heading.default">
				<div class="elementor-widget-container">
					<h3 class="elementor-heading-title elementor-size-default" style="color: rgb(21, 29, 61);">Los Angeles</h3>				</div>
				</div>
				<div class="elementor-element elementor-element-bc1f485 LocationsText elementor-widget elementor-widget-text-editor" data-id="bc1f485" data-element_type="widget" data-widget_type="text-editor.default">
				<div class="elementor-widget-container">
									<p>Location To Be<br>Announced</p>								</div>
				</div>
				<div class="elementor-element elementor-element-7f85c19 elementor-icon-list--layout-traditional elementor-list-item-link-full_width elementor-widget elementor-widget-icon-list" data-id="7f85c19" data-element_type="widget" data-widget_type="icon-list.default">
				<div class="elementor-widget-container">
							<ul class="elementor-icon-list-items">
							<li class="elementor-icon-list-item">
											<a href="tel:3109147300">

												<span class="elementor-icon-list-icon">
							<i aria-hidden="true" class="fas fa-phone-alt"></i>						</span>
										<span class="elementor-icon-list-text">(310) 914-7300</span>
											</a>
									</li>
						</ul>
						</div>
				</div>
				</div>
		<div data-particle_enable="false" data-particle-mobile-disabled="false" class="elementor-element elementor-element-3a339d7 Location e-con-full e-flex e-con e-child" data-id="3a339d7" data-element_type="container" data-location="map-sanfrancisco">
				<div class="elementor-element elementor-element-c054493 OfficeLocation__heading elementor-widget elementor-widget-heading" data-id="c054493" data-element_type="widget" data-widget_type="heading.default">
				<div class="elementor-widget-container">
					<div class="elementor-heading-title elementor-size-default">Washington D.C.</div>				</div>
				</div>
				<div class="elementor-element elementor-element-e438da3 LocationsText elementor-widget elementor-widget-text-editor" data-id="e438da3" data-element_type="widget" data-widget_type="text-editor.default">
				<div class="elementor-widget-container">
									<p>Hart Senate Office Building #112<br>Office Building<br>Washington, DC 20510</p>								</div>
				</div>
				<div class="elementor-element elementor-element-297d741 elementor-icon-list--layout-traditional elementor-list-item-link-full_width elementor-widget elementor-widget-icon-list" data-id="297d741" data-element_type="widget" data-widget_type="icon-list.default">
				<div class="elementor-widget-container">
							<ul class="elementor-icon-list-items">
							<li class="elementor-icon-list-item">
											<a href="tel:2022243841">

												<span class="elementor-icon-list-icon">
							<i aria-hidden="true" class="fas fa-phone-alt"></i>						</span>
										<span class="elementor-icon-list-text">(202) 224-3841</span>
											</a>
									</li>
						</ul>
						</div>
				</div>
				<div class="elementor-element elementor-element-3d9103e ButtonWrapper--location elementor-widget elementor-widget-button" data-id="3d9103e" data-element_type="widget" data-widget_type="button.default">
				<div class="elementor-widget-container">
									<div class="elementor-button-wrapper">
					<a class="elementor-button elementor-button-link elementor-size-sm" href="https://www.google.com/maps/place/Hart+Senate+Office+Building/@38.8922102,-77.0066133,17z/data=!3m1!4b1!4m5!3m4!1s0x89b7b825fc7f827d:0x8c216f696b14bfb4!8m2!3d38.8922102!4d-77.0044246" target="_blank">
						<span class="elementor-button-content-wrapper">
						<span class="elementor-button-icon">
				<i aria-hidden="true" class="fas fa-long-arrow-alt-right"></i>			</span>
									<span class="elementor-button-text">Directions</span>
					</span>
					</a>
				</div>
								</div>
				</div>
				</div>
				</div>
		<div data-particle_enable="false" data-particle-mobile-disabled="false" class="elementor-element elementor-element-da67173 e-con-full elementor-hidden-tablet elementor-hidden-mobile e-flex e-con e-child" data-id="da67173" data-element_type="container" data-settings="{&quot;background_background&quot;:&quot;classic&quot;}">
		<div data-particle_enable="false" data-particle-mobile-disabled="false" class="elementor-element elementor-element-9402aa0 e-con-full e-flex e-con e-child" data-id="9402aa0" data-element_type="container">
				<div class="elementor-element elementor-element-7a729e6 elementor-hidden-mobile elementor-widget elementor-widget-html" data-id="7a729e6" data-element_type="widget" data-widget_type="html.default">
				<div class="elementor-widget-container">
					<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="521px" height="591px" class="js-map">
<path fill-rule="evenodd" fill="rgb(143, 201, 188)" class="js-stateShape" d="M15.125,0.9 L210.159,0.84 L211.199,98.506 L211.199,156.290 L211.199,189.780 L246.729,220.642 L344.766,306.6 L488.860,431.426 C488.860,433.395 488.860,436.22 488.860,438.649 C488.860,439.305 488.860,439.305 488.860,439.962 C489.518,441.275 490.834,441.932 492.150,443.245 C492.808,444.559 493.466,445.872 494.124,447.185 C495.440,448.498 497.414,449.155 498.730,450.468 C500.46,452.438 498.72,455.721 499.387,457.692 C500.46,459.5 501.362,459.661 501.362,460.975 C502.19,462.288 500.703,463.601 501.362,464.914 C502.19,466.884 504.651,466.228 506.625,466.884 C508.599,467.541 509.915,469.511 511.889,470.168 C512.547,470.168 513.205,470.168 513.205,470.824 C513.863,471.481 513.863,472.138 514.521,472.794 C515.179,473.451 515.837,473.451 516.495,474.108 C517.153,474.764 517.153,475.421 516.495,476.78 C516.495,476.78 515.837,476.78 515.179,476.78 C513.863,476.734 513.205,478.704 511.889,479.361 C511.231,480.18 509.915,480.18 509.257,480.674 C507.941,481.987 507.283,483.301 505.967,484.614 C505.309,485.270 503.993,485.927 502.677,485.927 L502.19,485.927 C502.677,485.927 502.677,486.584 502.677,487.241 C502.677,487.897 502.677,488.554 502.677,489.210 C502.677,489.867 502.19,489.867 502.19,490.524 C501.362,491.181 502.19,491.837 501.362,493.150 C501.362,493.807 500.703,494.464 500.46,495.120 C499.387,495.120 498.730,496.434 498.72,497.90 C498.72,498.404 498.730,499.60 498.730,500.373 C498.730,501.30 498.730,501.30 498.730,501.687 C498.730,503.0 498.730,503.657 498.730,504.970 C498.730,506.283 498.730,506.940 499.387,508.253 C499.387,508.910 500.46,509.567 500.46,510.223 C500.46,510.223 500.46,510.880 500.46,511.536 C500.46,512.193 499.387,512.850 499.387,512.850 C498.730,513.506 498.730,514.163 498.730,514.820 C498.730,514.820 498.730,514.820 498.730,515.477 C498.730,516.133 498.730,515.477 498.730,515.477 C498.730,518.103 498.730,520.73 498.730,522.700 C498.730,523.356 498.72,524.670 497.414,524.670 C496.756,525.326 496.98,525.326 496.98,525.326 C494.782,526.639 495.440,529.923 493.466,530.579 C492.808,530.579 491.492,530.579 490.834,531.236 C490.176,531.893 490.176,533.206 490.176,533.863 C490.834,535.833 491.492,537.802 491.492,539.772 C492.150,541.742 492.808,543.712 492.150,545.682 C492.808,546.339 492.150,547.652 492.150,548.309 C492.150,548.965 491.492,548.965 491.492,549.622 C490.834,550.935 492.150,552.249 492.808,552.905 C493.466,553.562 493.466,554.875 494.124,555.532 C495.440,556.188 496.756,555.532 498.72,555.532 C499.387,555.532 500.703,555.532 502.19,555.532 C502.677,555.532 503.993,555.532 503.993,556.845 C504.651,557.502 503.993,558.158 503.993,559.472 C503.993,560.785 504.651,562.98 505.309,563.412 C505.967,564.725 506.625,565.381 506.625,566.695 L506.625,567.351 C506.625,568.8 505.967,568.665 505.309,568.665 C504.651,568.665 503.993,569.321 503.335,569.321 C502.677,569.978 502.19,571.291 502.19,572.604 C502.19,573.918 500.703,575.231 500.46,575.231 C499.387,575.231 499.387,575.231 498.730,575.231 C498.72,574.574 496.756,574.574 496.98,573.918 C496.98,571.291 495.440,571.291 494.782,571.291 C494.124,571.291 493.466,571.291 493.466,571.948 C493.466,572.604 493.466,573.261 492.808,573.261 L434.907,581.798 L365.821,590.991 C365.163,590.334 365.821,589.21 365.163,588.364 C365.163,587.51 364.505,585.738 363.847,584.424 C363.189,583.111 362.531,581.798 362.531,581.141 L362.531,580.484 C361.873,579.828 361.215,580.484 361.215,581.141 C361.215,581.798 361.215,582.454 360.557,583.111 C360.557,583.111 360.557,583.111 359.899,583.111 C359.899,583.111 359.899,583.111 359.899,582.454 C359.899,579.828 359.241,577.858 359.899,575.231 C359.899,573.918 358.583,573.918 357.925,572.604 C357.925,571.948 357.925,571.948 357.925,571.291 C358.583,569.321 358.583,566.695 357.925,564.68 C357.267,561.442 355.951,559.472 355.293,557.502 C354.635,555.532 353.319,553.562 352.661,552.249 C351.345,549.622 350.29,547.652 348.56,545.682 C346.82,544.369 345.424,541.742 343.450,541.86 C342.792,541.86 342.134,541.86 341.476,540.429 C339.502,539.772 338.844,536.489 336.212,535.833 C335.554,535.833 334.238,535.833 333.580,535.176 C332.922,535.176 332.922,534.519 332.922,534.519 C332.265,533.206 331.606,532.549 330.290,531.236 C328.975,529.266 325.685,527.953 323.53,527.296 C322.395,527.296 321.737,527.296 321.79,526.639 C319.763,525.983 319.763,524.13 319.105,522.700 C318.447,522.43 317.789,521.386 317.131,521.386 C315.157,520.73 313.842,518.760 311.867,517.446 C311.210,517.446 311.210,516.790 310.551,516.790 C309.894,516.790 309.236,517.446 309.236,517.446 C308.578,518.103 307.262,517.446 306.604,518.103 C305.946,518.760 305.946,519.416 305.288,520.73 C304.630,520.730 303.314,520.73 302.656,519.416 C301.998,518.760 300.682,518.103 300.24,518.103 C299.366,518.103 299.366,518.103 298.708,518.760 C298.50,518.760 297.392,517.446 297.392,516.790 C297.392,516.133 298.50,514.820 298.708,514.163 C299.366,513.506 299.366,512.193 299.366,511.537 C300.24,510.880 298.708,509.567 298.50,508.910 C296.76,506.940 295.418,503.0 292.787,501.687 C291.471,501.30 290.155,501.30 288.839,501.30 C287.523,501.30 286.207,501.30 284.891,501.30 C283.575,501.30 282.259,501.30 280.943,501.687 C280.285,501.687 279.627,502.343 278.969,502.343 C278.311,502.343 277.653,502.343 276.995,502.343 C275.680,502.343 274.364,501.687 273.705,501.687 C272.389,501.687 270.416,501.30 269.100,499.717 C267.784,498.404 265.152,497.747 263.836,497.90 C262.520,497.747 261.204,497.90 260.546,496.434 C259.230,495.777 258.572,495.120 257.914,493.807 C257.256,492.494 255.941,491.837 255.282,490.524 C254.625,489.211 254.625,488.554 253.966,487.241 C253.309,486.584 252.651,485.928 251.993,485.271 C250.677,484.614 250.19,483.957 248.703,483.301 C244.755,480.674 240.807,478.704 236.859,478.48 C235.543,478.48 234.886,478.48 233.570,478.48 C232.254,478.48 231.596,478.704 230.280,478.704 C228.964,478.704 227.648,477.391 226.332,477.391 C225.674,477.391 224.358,478.48 223.700,478.48 C222.384,478.48 221.726,477.391 220.410,477.391 C219.94,476.734 217.120,475.421 215.147,475.421 C213.831,475.421 212.515,476.78 211.857,475.421 C211.199,475.421 210.541,474.764 209.883,474.764 C207.251,473.451 204.619,475.421 201.987,474.108 C201.329,474.108 200.671,473.451 200.13,473.451 C199.356,473.451 198.697,473.451 198.40,473.451 C196.66,474.108 194.92,474.108 191.460,474.764 C190.802,474.108 190.802,472.794 190.144,472.138 C190.144,471.481 189.486,471.481 188.828,470.824 C188.828,470.168 188.828,470.168 188.170,469.511 C186.854,467.541 184.880,467.541 182.906,466.885 C181.590,466.228 181.590,465.571 181.590,464.915 C181.590,464.258 182.248,464.258 182.248,463.602 C182.248,462.945 182.248,462.288 182.248,461.631 C182.906,459.661 183.564,457.692 182.248,455.721 C182.248,455.65 181.590,455.65 181.590,454.408 C181.590,453.752 182.248,453.752 182.248,453.95 C182.248,451.782 182.248,451.125 182.906,449.812 L182.248,449.155 C182.248,447.842 181.590,446.529 180.932,445.872 C180.274,445.215 180.274,445.215 180.274,444.559 C180.274,443.902 180.932,443.245 180.932,442.589 C180.932,439.306 183.564,436.679 182.248,433.395 C181.590,431.426 178.958,429.456 176.985,429.456 C176.327,429.456 175.669,429.456 175.11,429.456 C174.353,429.456 174.353,428.799 174.353,428.799 C173.695,428.143 173.37,428.143 172.379,428.143 C171.63,427.486 169.747,426.829 169.89,425.516 C169.89,425.516 168.431,424.859 168.431,424.203 C168.431,423.546 169.747,422.889 169.89,422.233 C169.89,420.263 169.747,418.293 169.89,416.323 C168.431,414.353 167.115,413.40 165.141,412.383 C164.483,412.383 164.483,412.383 163.825,412.383 C163.825,412.383 163.167,412.383 163.167,411.726 C161.851,410.413 161.194,409.756 160.536,408.443 C160.536,407.786 159.878,407.786 159.878,407.130 C159.220,405.816 157.246,405.160 157.246,403.847 C155.930,403.847 155.272,401.877 154.614,401.877 L153.956,401.877 C153.298,401.877 152.640,401.220 152.640,400.563 C152.640,400.563 151.982,400.563 151.982,401.220 C149.350,400.563 148.34,400.563 147.376,399.907 L147.376,399.250 C146.718,397.937 146.718,396.623 146.60,395.967 C145.402,394.654 144.744,393.340 144.86,392.27 C142.770,390.57 140.796,388.744 139.480,386.774 C138.165,386.774 137.507,385.460 137.507,384.147 C137.507,382.834 137.507,382.177 136.849,380.864 C136.191,378.894 133.559,377.581 132.243,375.611 C130.269,372.984 130.269,369.701 127.637,367.731 C125.663,366.418 123.31,365.761 121.716,363.791 C121.57,363.135 121.57,362.478 121.57,361.821 C120.400,360.508 119.84,359.851 117.768,359.195 C115.794,357.881 115.794,355.255 115.136,352.628 C115.136,351.971 115.136,351.315 115.136,350.658 C115.136,350.1 114.478,349.345 114.478,349.345 C113.820,348.32 114.478,345.405 113.162,344.748 C113.820,344.748 113.820,343.435 113.820,342.778 C113.820,342.122 113.162,341.465 113.162,340.809 C113.162,340.152 113.162,338.838 113.820,338.182 C113.820,337.525 114.478,336.869 114.478,336.869 L115.136,336.869 C115.794,337.525 117.110,337.525 117.768,338.182 C118.426,337.525 119.742,336.212 119.742,335.555 C120.400,334.242 121.57,331.615 121.57,330.302 C121.716,328.989 121.716,327.675 121.716,326.362 C121.716,325.705 121.57,325.49 120.400,323.736 C119.84,321.765 118.426,319.796 117.110,317.825 C116.452,317.169 115.794,315.856 115.136,315.856 C114.478,315.856 113.820,315.856 113.162,316.512 C110.530,317.825 107.898,317.825 105.266,316.512 C102.634,315.199 100.661,313.229 99.345,310.603 C98.687,309.289 98.687,308.633 97.371,307.319 C98.29,308.633 97.371,308.633 97.371,308.633 C96.713,308.633 96.713,308.633 96.55,308.633 L96.55,307.976 C96.55,307.319 95.397,306.663 94.739,306.663 C94.81,306.6 93.423,305.350 92.765,304.693 L92.107,304.36 C92.107,304.36 92.107,303.379 92.107,302.723 C92.107,300.753 92.107,298.783 92.765,296.813 C93.423,294.843 92.765,292.873 92.107,291.560 C91.449,288.933 90.791,286.963 89.475,284.337 C88.817,284.993 87.501,284.337 87.501,283.680 C87.501,283.24 87.501,281.710 87.501,281.53 C87.501,280.397 87.501,279.740 87.501,279.84 C87.501,278.427 87.501,278.427 88.159,278.427 C88.817,277.114 89.475,275.800 89.475,273.830 C89.475,273.174 89.475,273.174 89.475,272.517 C88.817,270.547 90.133,267.921 88.817,265.951 C88.159,265.294 87.501,264.638 86.843,263.980 C85.527,263.324 84.212,262.11 82.896,261.354 C82.238,261.354 82.238,260.698 81.580,260.698 C80.264,260.41 78.948,260.698 77.632,260.41 C76.316,258.728 75.658,257.414 74.342,256.101 C73.684,254.788 72.368,253.474 71.52,252.818 C69.736,252.161 67.762,251.505 67.104,252.818 C67.104,252.818 67.104,253.474 66.446,253.474 L65.788,253.474 C65.131,253.474 63.815,253.474 63.815,252.818 C63.815,252.161 63.815,252.161 63.815,251.505 C64.473,249.534 65.131,248.221 65.788,246.908 C66.446,246.251 66.446,245.594 67.104,244.281 C67.104,243.625 67.104,242.311 65.788,242.311 C65.131,240.998 65.131,239.685 65.131,239.28 C65.131,238.371 65.131,238.371 65.131,237.715 C65.131,237.715 65.131,237.58 64.473,237.58 L64.473,236.402 C64.473,235.88 63.157,234.432 61.841,234.432 L61.183,234.432 L61.183,234.432 C61.183,232.462 60.525,230.492 59.209,229.179 C58.551,227.209 57.235,225.239 55.919,223.925 C55.261,223.269 53.945,223.269 52.629,222.612 C50.655,221.955 49.339,219.985 48.681,218.672 C48.681,218.15 48.23,218.15 48.23,217.359 C48.23,216.702 47.365,216.702 46.707,216.46 C46.50,215.389 45.392,214.76 45.392,212.762 C42.102,208.823 38.812,204.883 35.522,201.599 C34.206,199.629 32.232,197.659 30.916,195.689 C30.258,195.33 30.258,194.376 29.600,193.720 C29.600,193.63 29.600,191.749 30.258,191.749 C30.916,189.780 30.916,187.153 30.258,185.183 C30.258,183.870 29.600,183.213 29.600,181.900 C29.600,181.243 29.600,181.243 28.942,180.587 C28.942,179.930 28.284,179.930 28.284,179.273 C27.627,177.960 26.968,175.990 26.968,174.20 C26.311,172.50 26.311,170.80 25.653,168.110 C24.995,166.140 24.995,163.514 26.311,161.544 C26.968,160.230 27.627,159.574 28.284,158.261 C28.942,156.947 28.942,155.634 28.284,154.321 C28.284,153.664 27.627,153.664 27.627,153.7 C27.627,152.351 27.627,151.694 27.627,151.38 C28.284,149.68 26.968,146.441 25.653,145.128 C25.653,143.815 25.653,142.501 25.653,141.188 L25.653,140.531 C25.653,140.531 24.995,140.531 24.995,139.875 C24.337,139.218 24.337,138.561 24.337,137.904 C24.337,136.591 23.21,135.935 22.363,134.621 L22.363,133.965 L21.705,133.308 C21.47,132.651 20.389,131.995 19.731,130.681 C19.731,130.25 19.73,128.711 18.415,128.55 C17.757,127.398 17.99,127.398 16.441,126.741 C15.125,125.428 14.467,123.458 13.809,121.488 C11.835,118.862 8.545,116.892 5.914,114.922 C5.256,113.609 3.940,112.295 3.282,111.639 C2.624,110.982 1.966,110.982 1.966,110.325 C1.966,109.669 2.624,108.356 2.624,107.699 C2.624,107.42 2.624,106.385 1.966,105.729 C1.966,105.72 1.966,104.416 1.966,103.759 C1.966,101.789 0.650,100.476 0.7,99.162 C0.7,98.506 0.7,97.849 0.7,97.849 C0.650,95.223 1.966,92.596 3.282,90.626 C3.940,89.970 4.598,89.313 4.598,87.999 C6.572,84.716 7.888,80.776 9.861,77.493 C10.519,76.180 11.177,74.210 11.835,72.896 C12.493,71.583 13.151,69.613 13.809,68.300 C14.467,66.987 15.125,65.17 14.467,63.703 C14.467,63.703 14.467,63.47 13.809,63.47 C13.809,63.47 13.809,63.47 13.151,63.47 C12.493,63.47 11.835,62.390 11.835,62.390 C11.177,61.734 11.177,60.420 11.835,59.763 C12.493,59.107 12.493,57.794 13.151,57.137 C13.809,56.480 13.809,55.167 13.809,54.510 C13.809,53.854 13.809,53.197 14.467,52.540 C14.467,51.227 15.125,50.571 15.783,49.257 C16.441,47.944 16.441,47.287 16.441,45.974 C16.441,44.661 17.99,43.348 17.99,42.34 C17.99,40.64 17.99,37.437 16.441,35.468 C16.441,34.811 16.441,34.811 16.441,34.154 C16.441,33.498 16.441,32.185 15.783,31.528 C15.783,30.871 15.783,30.871 15.125,30.215 C15.125,29.558 15.125,28.901 14.467,28.245 C14.467,26.931 14.467,25.618 13.809,24.305 C13.809,22.335 13.151,20.365 11.177,19.51 C10.519,19.51 9.204,19.51 8.545,18.395 C7.888,17.738 7.888,16.425 7.888,15.768 C7.888,15.112 8.545,14.455 9.204,13.798 C15.783,8.545 15.125,3.949 15.125,0.9 Z" style="stroke: rgb(25, 100, 95); stroke-dashoffset: 0px; stroke-dasharray: none; fill: rgb(143, 201, 188);"></path>
 <g class="js-MapPoints">
<text kerning="auto" fill="rgb(0, 0, 0)" transform="matrix(0.92566,0,0,0.92555,257.97079,566.62779)" font-size="12.965px" style="translate: none; rotate: none; scale: none; opacity: 1; visibility: inherit;" data-svg-origin="0 -12.603680610656738"><tspan font-size="12.965px" font-family="Montserrat" font-weight="bold" fill="#152251">SAN DIEGO</tspan></text>
<path id="map-sandiego" fill-rule="evenodd" fill="rgb(21, 34, 81)" d="M353.189,555.827 C356.503,555.827 359.189,558.513 359.189,561.827 C359.189,565.141 356.503,567.827 353.189,567.827 C349.875,567.827 347.189,565.141 347.189,561.827 C347.189,558.513 349.875,555.827 353.189,555.827 Z" style="fill: rgb(0, 29, 56);" class=""></path>
<text kerning="auto" fill="rgb(0, 0, 0)" transform="matrix(0.92566,0,0,0.92555,327.89392,492.62779)" font-size="12.965px" style="translate: none; rotate: none; scale: none; opacity: 1; visibility: inherit;" data-svg-origin="0 -12.603680610656738"><tspan font-size="12.965px" font-family="Montserrat" font-weight="bold" fill="#152251">LOS ANGELES</tspan></text>
<path id="map-downtownla" fill-rule="evenodd" fill="rgb(21, 34, 81)" d="M317.189,481.827 C320.503,481.827 323.189,484.513 323.189,487.827 C323.189,491.140 320.503,493.827 317.189,493.827 C313.875,493.827 311.189,491.140 311.189,487.827 C311.189,484.513 313.875,481.827 317.189,481.827 Z" style="fill: rgb(0, 29, 56);" class=""></path>
<text kerning="auto" fill="rgb(0, 0, 0)" transform="matrix(0.92566,0,0,0.92555,231.44431,321.62779)" font-size="12.965px" style="translate: none; rotate: none; scale: none; opacity: 1; visibility: inherit;" data-svg-origin="0 -12.603680610656738"><tspan font-size="12.965px" font-family="Montserrat" font-weight="bold" fill="#152251">FRESNO</tspan></text>
<path id="map-fresno" fill-rule="evenodd" fill="rgb(21, 34, 81)" d="M217.159,311.180 C220.473,311.180 223.159,313.866 223.159,317.180 C223.159,320.494 220.473,323.180 217.159,323.180 C213.846,323.180 211.159,320.494 211.159,317.180 C211.159,313.866 213.846,311.180 217.159,311.180 Z" style="fill: rgb(0, 29, 56);" class=""></path>
<text kerning="auto" fill="rgb(0, 0, 0)" transform="matrix(0.92566,0,0,0.92555,103.94257,278.62779)" font-size="12.965px" style="translate: none; rotate: none; scale: none; opacity: 1; visibility: inherit;" data-svg-origin="0 -12.603680610656738"><tspan font-size="12.965px" font-family="Montserrat" font-weight="bold" fill="#152251">SAN FRANCISCO</tspan></text>
<path id="map-sanfrancisco" fill-rule="evenodd" fill="rgb(21, 34, 81)" d="M90.267,267.390 C93.581,267.390 96.267,270.76 96.267,273.390 C96.267,276.704 93.581,279.390 90.267,279.390 C86.954,279.390 84.267,276.704 84.267,273.390 C84.267,270.76 86.954,267.390 90.267,267.390 Z" style="fill: rgb(9, 101, 220);" class="selected"></path>
 </g>
<!--<text kerning="auto"  fill="rgb(0, 0, 0)" transform="matrix( 0.92565555930627, 0, 0, 0.92554694457367,39.3834735378449, 221.627734722868)" font-size="12.965px"><tspan font-size="12.965px" font-family="Montserrat" font-weight="bold" fill="#152251">SACRAMENTO</tspan></text>-->
<!--<path id="map-sacramento" fill-rule="evenodd"  fill="rgb(21, 34, 81)"-->
<!-- d="M152.730,211.6 C156.43,211.6 158.730,213.693 158.730,217.6 C158.730,220.320 156.43,223.6 152.730,223.6 C149.416,223.6 146.730,220.320 146.730,217.6 C146.730,213.693 149.416,211.6 152.730,211.6 Z"/>-->
</svg>				</div>
				</div>
				<div class="elementor-element elementor-element-201cd39 elementor-widget elementor-widget-html" data-id="201cd39" data-element_type="widget" data-widget_type="html.default">
				<div class="elementor-widget-container">
					<script>
  jQuery(document).ready(function($) {
    $('.Location').hover(function() {
      var loc = $(this).data('location');
      $('#' + loc).css('fill', '#0965DC');
        $('#' + loc).addClass('selected')
      $(this).find('h3').css('color', '#0965DC');
    }, function() {
      var loc = $(this).data('location');
      $('#' + loc).css('fill', '#001d38');
      $('#' + loc).removeClass('selected')
      $(this).find('h3').css('color', '#151d3d');
    })
  })
</script>				</div>
				</div>
				</div>
				</div>
				</div>
				</div>
```


5. Last step, we'll need to insure human validation. I'm thinking we'll do this during runtime; that is, we should show an image of the rendered HTML snippet from where the scraped district_office information was sourced along with the raw data that was retrieved and is slated to be insertted into our database. (Should we do provenance tracking/logging?). And perhaps a columnm identifier to denote that this information was sourced from our scraper. If and once validated and insertted into our database, we'll store the image and JSON pairs in a folder, so that if we share the data, they can easily validate it themselves as well - so detailed logging is a requirement. 
