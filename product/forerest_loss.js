// Initialize the UI. 
//Clear the default UI since we're adding our own main and map panels.
ui.root.clear();
var mapPanel = ui.Map();
ui.root.widgets().reset([mapPanel]);
mapPanel.setCenter(107.492521, 16.380931, 10)

/*
MAKE MAIN PANEL
*/

var colors = {
  'cyan': '#24C1E0',
  'transparent': '#ffffff',
  'gray': '#ffffff'
};

var TITLE_STYLE = {
  fontWeight: 'bold',
  fontSize: '16px',
  padding: '8px',
  color: '#eb2f05',
  backgroundColor: colors.transparent,
};

var SUBTITLE_STYLE = {
  fontSize: '14px',
  fontWeight: 'bold',
  color: '#0f0606',
  padding: '2px',
  backgroundColor: colors.transparent,
};


var PARAGRAPH_STYLE = {
  fontSize: '14px',
  fontWeight: 'bold',
  color: '#9E9E9E',
  padding: '8px',
  backgroundColor: colors.transparent,
};

var SUBPARAGRAPH_STYLE = {
  fontSize: '13px',
  fontWeight: 'bold',
  color: '#055deb',
  padding: '2px',
  backgroundColor: colors.transparent,
};

var LABEL_STYLE = {
  fontWeight: '50',
  textAlign: 'center',
  fontSize: '11px',
  backgroundColor: colors.transparent,
};

var THUMBNAIL_WIDTH = 128;

var BORDER_STYLE = '4px solid rgba(97, 97, 97, 0.05)';


var mainPanel = ui.Panel({
  layout: ui.Panel.Layout.flow('vertical', true),
  style: {
    stretch: 'horizontal',
    height: '60%',
    width: '350px',
    backgroundColor: colors.gray,
    border: BORDER_STYLE,
    position: 'top-left'
  }
});

// Add the app title to the side panel
var titleLabel = ui.Label('ỨNG DỤNG PHÁT HIỆN SỚM MẤT RỪNG ÁP DỤNG KHU VỰC TỈNH THỪA THIÊN HUẾ', TITLE_STYLE);
mainPanel.add(titleLabel);

// Add the app description to the main panel
var descriptionText =
  'Ứng dụng đang trong quá trình thử nghiệm. Kết quả mang tính chất tham khảo và cần đối chiếu với hiện trường để xác minh thông tin thực tế.' //Nhóm tác giả: Vũ Văn Thái, Nguyễn Hải Hòa, Lê Thị Quỳnh Hoa, Nguyễn Minh Ngọc, Tống Hoàng Phước Hiếu' 
var descriptionLabel = ui.Label(descriptionText, PARAGRAPH_STYLE);
mainPanel.add(descriptionLabel);

// SELECT DATE 
var firstSubTitle_text = '1) Chọn ngày bắt đầu và ngày kết thúc';
var firstSubTitle = ui.Label(firstSubTitle_text, SUBTITLE_STYLE);
mainPanel.add(firstSubTitle);

var firstSubParagraph_text = 'Lưu ý: Người dùng cần thay đổi thời gian và chọn khu vực quan tâm và chọn Apply để chạy ứng dụng. Trong quá trình chạy, dữ liệu quá lớn có thể dẫn đến treo duyệt web. Nếu trình duyệt web hỏi chờ (wait) hoặc thoát (exit), vui lòng chọn chờ (wait). Sau khoảng 2 phút sẽ trả về kết quả và cho phép tải về dạng GeoJson.' //Ứng dụng sẽ tự chọn kỳ sau (ngày kết thúc là hôm nay, và ngày bắt đầu là lùi lại 10 ngày), và kỳ trước cách kỳ đầu 10 ngày. Người dùng có thể chọn lại khoảng thời gian và khu vực sau đó chọn Apply. Thời gian chờ kết quả khoảng từ 2 phút.';
var firstSubParagraph = ui.Label(firstSubParagraph_text, SUBPARAGRAPH_STYLE);
mainPanel.add(firstSubParagraph);


var t2_titleStartDate = ui.Label('Kỳ sau - ngày bắt đầu:')
var t2_titleEndDate = ui.Label('Kỳ sau - ngày kết thúc:')
var gach_phancach = ui.Label('--------------------------------------------------------')
var t1_titleEndDate = ui.Label('Kỳ đầu - ngày kết thúc:')
var t1_titleStartDate = ui.Label('Kỳ đầu - ngày bắt đầu:')

//DATE SELECT

//Get Today's date and pass it as default End date. 
var now = new Date();
var nowStr = now.toLocaleDateString('en-CA');

//kỳ sau - Ngày kết thúc = now
var t2_endDate = ui.Textbox({
  value: nowStr,
  placeholder: 'Nhập ngày kết thúc...',
  style: {
    margin: '8px',
    width: '70%'
  },
  onChange: function(end) {
    t2_endDate.setValue(end);
  }
});

//Get Last month's date date and pass it as default Start date.
var dateNow = ee.Date(nowStr);
var lastMonth = dateNow.advance(-15, 'day').format("YYYY-MM-dd");
var kydau_kethuc = dateNow.advance(-30, 'day').format("YYYY-MM-dd");
var kydau_batdau = dateNow.advance(-45, 'day').format("YYYY-MM-dd");

//Kỳ sau - bắt đầu
var t2_startDate = ui.Textbox({
  value: lastMonth.getInfo(),
  placeholder: 'Ngày bắt đầu...',
  style: {
    margin: '8px',
    width: '70%'
  },
  onChange: function(start) {
    t2_startDate.setValue(start);
  }
});
//kỳ đầu - kết thúc
var t1_endDate = ui.Textbox({
  value: kydau_kethuc.getInfo(),
  placeholder: 'Ngày kết thúc kỳ đầu',
  style: {
    margin: '8px',
    width: '70%'
  },
  onChange: function(start) {
    t1_endDate.setValue(start);
  }
});
//kỳ đầu - bắt đầub
var t1_startDate = ui.Textbox({
  value: kydau_batdau.getInfo(),
  placeholder: 'Ngày kết thúc kỳ đầu',
  style: {
    margin: '8px',
    width: '70%'
  },
  onChange: function(start) {
    t1_startDate.setValue(start);
  }
});


mainPanel.add(t1_titleStartDate);
mainPanel.add(t1_startDate);
mainPanel.add(t1_titleEndDate);
mainPanel.add(t1_endDate);
mainPanel.add(gach_phancach);

mainPanel.add(t2_titleStartDate);
mainPanel.add(t2_startDate);
mainPanel.add(t2_titleEndDate)
mainPanel.add(t2_endDate);
// Add boundary
var subtittle_rg = '2) Chọn khu vực cần quan tâm:';
var secondSubtittle_rg = ui.Label(subtittle_rg, SUBTITLE_STYLE);
mainPanel.add(secondSubtittle_rg);

var communeName = 'Thua Thien Hue'
var commune = ee.FeatureCollection('users/lethiquynhhoa/vietnam/gadm36_VNM_2_Districts').filter(ee.Filter.eq('VARNAME_1', communeName))

var plot = ee.FeatureCollection('users/lethiquynhhoa/Hue/MasK_forest_Hue')


// type of provinceNames: List
var communeNames = commune.aggregate_array('NAME_2')



// Empty Dropdowns
var districtDD = ui.Select([], 'Loading..')

// Load province

districtDD.style().set({
  margin: '8px',
  width: '70%'
})

communeNames.evaluate(function(evaluatedCommuneNames) {
  districtDD.items().reset(evaluatedCommuneNames)
  districtDD.setPlaceholder('Chọn huyện')
})


//Add to main panel  
mainPanel.add(districtDD);

// Use a SplitPanel so it's possible to resize the two panels.
var splitPanel = ui.SplitPanel({
  firstPanel: mainPanel,
  secondPanel: mapPanel,
  orientation: 'horizontal',
  style: {
    stretch: 'both'
  }
});

// Set the SplitPanel as the only thing in root.
ui.root.widgets().reset([splitPanel]);

/*

PROCESSING STARTS HERE

*/
var area_Filter = 0.1 // Đơn vị Hecta
//Threshold remove cloud pixel 0-100 (-->100: mây vẫn còn nhiều, 0-30: giảm bớt mây)
var cloudy = 25

var threshold = -0.28
var threshold_rm_ndvi = 0.59 //Sử dụng check bước 2 và bước 4 :Ngưỡng NDVI để check nếu tất cả các tháng > 0.35 --> Rừng ổn định


var threshold_ndvi_t234 = 0.45 //Ngưỡng NDVI cho 3 tháng 2,3,4 nếu cả 3 tháng <0.45 -->Rừng khộp 
var threshold_ndvi_m_now = 0.2 //Ngưỡng NDVI cho khi so sánh cho tháng hiện tại, nếu chuỗi có tháng hiện tại <0.2 (true) --> Mất rừng còn các tháng khác >0.55
var zoomLevel = 12
var style_result_final = {
  color: '#d2ff00',
  fillColor: '00000000'
}
var bands = ['B4', 'B3', 'B2']


var drawButton = ui.Button({
  label: 'APPLY',
  style: {
    textAlign: 'center',
    stretch: 'horizontal',
    margin: '2% 10% 2% 10%',
    width: '40%'
  },
  onClick: function() {

    var district_Name = districtDD.getValue()
    var Bound = ee.Feature(commune.filterMetadata('NAME_2', 'equals', district_Name).first()).geometry()


    //Define dates
    var t1_date_start = t1_startDate.getValue(); //Kỳ đầu - bắt đầu
    var t1_date_end = t1_endDate.getValue(); //Kỳ đầu - kết thúc
    var t2_date_start = t2_startDate.getValue(); //Kỳ sau - bắt đầu
    var t2_date_end = t2_endDate.getValue(); //Kỳ sau - kết thúc

    var getS2_SR_CLOUD_PROBABILITY = function() {
      var innerJoined = ee.Join.inner().apply({
        primary: ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED"),
        secondary: ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY"),
        condition: ee.Filter.equals({
          leftField: 'system:index',
          rightField: 'system:index'
        })
      });
      var mergeImageBands = function(joinResult) {
        return ee.Image(joinResult.get('primary'))
          .addBands(joinResult.get('secondary'));
      };
      var newCollection = innerJoined.map(mergeImageBands);
      return ee.ImageCollection(newCollection);
    };
    var s2_nearly = getS2_SR_CLOUD_PROBABILITY().filterDate('2017-01-01', nowStr).filterBounds(Bound);

    var ST2_before_nocloud = getS2_SR_CLOUD_PROBABILITY()
      .filterDate(t1_date_start, t1_date_end)
      .filterBounds(Bound)
      .sort('system:time_start', false);
    var ST2_after_nocloud = getS2_SR_CLOUD_PROBABILITY()
      .filterDate(t2_date_start, t2_date_end)
      .filterBounds(Bound)
      .sort('system:time_start', false);

    // Mask out clouds.
    var maskClouds = function(_img) {
      var cloudProbabilityThreshold = 40;
      var cloudMask = _img.select('probability').lt(cloudProbabilityThreshold);
      return _img.updateMask(cloudMask);
    };

    //Apply cloud mask
    var st2median_before = ST2_before_nocloud.map(maskClouds).mean().clip(Bound);
    var st2median_after = ST2_after_nocloud.map(maskClouds).mean().clip(Bound);

    //--------------END SWIPE----------------------------------
    // the normalized difference vegetation index
    var ndvi_before = st2median_before.normalizedDifference(['B8', 'B4']).clip(Bound);
    var ndvi_after = st2median_after.normalizedDifference(['B8', 'B4']).clip(Bound);

    var deltaNdvi = ndvi_after.subtract(ndvi_before).clip(Bound)

    // print (deltaNdvi.getInfo())

    //Reclass delta ndvi
    var reclassifiedImage = deltaNdvi
      .where(deltaNdvi.lte(threshold), 0)
      .where(deltaNdvi.gt(threshold), 1)


    //Reduce to vector 
    var forestloss_vector = reclassifiedImage.int().reduceToVectors({
      geometry: Bound,
      crs: 'EPSG:32648',
      scale: 30,
      geometryType: 'polygon',
      eightConnected: false,
      labelProperty: 'label',
      maxPixels: 3000000000
    });

    var forest_remove = forestloss_vector.filter(ee.Filter.lt('label', 1))

    var simple_fun = function(f) {
      // var simple = f.geometry().simplify(3);
      // return f.setGeometry(simple).set('area', simple.area(3).divide(10000)); //Add new field "area" and convert to units (ha)
      return f.set('area', f.geometry().area(0.09).divide(10000)); //Add new field "area" and convert to units (ha)
    }


    var forestloss_vector_simplify = forest_remove.map(simple_fun);


    var forestloss_filter_area = forestloss_vector_simplify.filter(ee.Filter.gt('area', area_Filter))

    // print('Step 1 - Số lô mất rừng ban đầu:', forestloss_filter_area.size())

    //ADD After ndvi and before NDVI to one images
    var merge_ndvi = ee.ImageCollection.fromImages([ndvi_before, ndvi_after])
    merge_ndvi = merge_ndvi.toBands();


    // Reset the bandnames
    var names_ndvi = merge_ndvi.bandNames();
    // rename the bandnames 
    var newNames_ndvi = names_ndvi.map(function(name) {
      var ind = names_ndvi.indexOf(name);
      return ee.String(names_ndvi.get(ind));
    });

    merge_ndvi = merge_ndvi.rename(newNames_ndvi);
    var forestloss_mean_ndvi = merge_ndvi.reduceRegions({
      collection: forestloss_filter_area,
      reducer: ee.Reducer.mean(),
      scale: 30,
    });


    //Remove ndvi trước và sau theo ngưỡng mô tả ở trên
    var forestloss_filtered_ndvi = forestloss_mean_ndvi.filter(ee.Filter.gt('0_nd', threshold_rm_ndvi)).filter(ee.Filter.lt('1_nd', threshold_rm_ndvi))
    // print('Step 2 - Số lô mất rừng khi lọc NDVI threshold : ', forestloss_filtered_ndvi.size())


    // JOIN SPATIAL FORESTLOST WITH PLOT
    // Instead of this intersection filter, compute the overlap between buffers and semgments

    var filter = ee.Filter.intersects({
      leftField: '.geo',
      rightField: '.geo',
    })

    // Create the join.
    var join_intersect = ee.Join.saveAll({
      matchesKey: 'intersects'
    })

    // Apply the join.

    var forestloss_intersect_KKR = join_intersect.apply(forestloss_filtered_ndvi, plot, filter);
    forestloss_intersect_KKR = forestloss_intersect_KKR.map(simple_fun)

    //REMOVE COLUMN NO NEED
    // Generic Function to remove a property from a feature
    var removeProperty = function(feat, property) {
      var properties = feat.propertyNames()
      var selectProperties = properties.filter(ee.Filter.inList('item', property).not())
      return feat.select(selectProperties)
    }
    // remove property thùa in each feature
    forestloss_intersect_KKR = forestloss_intersect_KKR.map(function(feat) {
      return removeProperty(feat, ['area', 'count', 'intersects', 'label'])
    })


    // print('Step 3 - Số lô còn lại sau khi clip với lớp KKR (thuộc QH+ khác RK thì lấy): ', forestloss_intersect_KKR.size());


    //add mean probalitity band to result
    var forestloss_remove_stableForest = st2median_after.select('probability').reduceRegions({
      collection: forestloss_intersect_KKR,
      reducer: ee.Reducer.mean(),
      scale: 30,
    });


    // Step 4: Loại các giá trị có mây hờ bằng cách đưa giá trị trung bình của band probability vào result

    var forestloss_result = forestloss_remove_stableForest.filter(ee.Filter.lte('mean', 5))
    forestloss_result = forestloss_result.map(simple_fun)

    // print('Step 4 - Số lô sau khi loại mây hờ (Cloud Probability >5)', forestloss_result.size())

    var nbr_images = s2_nearly.size().getInfo();
    // print (S2);
    // print (nbr_images);
    if (nbr_images === 0) {
      var dateLabel = ui.Label('Không có ảnh trong khoảng ngày tìm kiếm. Vui lòng chọn khoảng ngày khác', {
        fontSize: '14px',
        fontWeight: 'bold',
        color: '#FF0000',
        padding: '2px',
      });
    } else {
      var range = s2_nearly.reduceColumns(ee.Reducer.minMax(), ["system:time_start"]);
      var latest = ee.Date(range.get('max')).format("YYYY-MM-dd");
      //print (latest.getInfo());
      dateLabel = ui.Label(latest.getInfo(), {
        fontWeight: 'bold'
      });
    }



    //Set the visualisation parameters.
    var BandCompViz = {
      min: 0,
      max: 1800,
      gamma: [0.95, 1.1, 1]
    };

    mapPanel.clear()

    mapPanel.addLayer(st2median_before.select(bands).clip(Bound), BandCompViz, district_Name + '_ky dau_' + t1_date_start + '_to_' + t1_date_end);
    mapPanel.addLayer(st2median_after.select(bands).clip(Bound), BandCompViz, district_Name + '_ky sau_' + t2_date_start + '_to_' + t2_date_end);
    mapPanel.addLayer(forestloss_result.style(style_result_final), {}, 'Forest change detection');

    var visParams1 = {
      'bands': bands,
      'max': 1500,
      'gamma': 1.5,
      'forceRgbOutput': true
    };
    var st2median_before_download = st2median_before.visualize(visParams1).clip(Bound.bounds());
    var st2median_after_download = st2median_after.visualize(visParams1).clip(Bound.bounds());
    mapPanel.addLayer(plot, {}, 'Forest land', false)
    mapPanel.centerObject(Bound, 13)

    /*

ADD DATE PANEL

*/
    var inspector = ui.Panel({
      style: {
        position: 'top-right',
        padding: '8px 20px'
      }
    });

    var dateLabeltext = ui.Label('Ngày có ảnh gần nhất: ' + latest.getInfo(), {
      fontWeight: 'bold'
    });
    var forestlosstext = ui.Label('Số lô nghi ngờ mất rừng: ' + forestloss_result.size().getInfo(), {
      fontWeight: 'bold'
    })

    inspector.add(dateLabeltext);
    inspector.add(forestlosstext);


    var download_json = (ui.Label('Tải xuống lớp mất rừng (.GEOJSON)').setUrl((forestloss_result.getDownloadURL({
      format: 'GeoJSON',
      filename: t1_date_start + '_to_' + t2_date_end
    }))));

    //   var download_img1 = (ui.Label('Tải xuống ảnh vệ tinh kỳ đầu').setUrl((st2median_before_download.getDownloadURL({
    //   format: 'GeoTIFF',
    //   filename:t1_date_start+'_to_'+t1_date_end
    // }))));

    //   var download_img2 = (ui.Label('Tải xuống ảnh vệ tinh kỳ sau').setUrl((st2median_after_download.getDownloadURL({
    //   format: 'GeoTIFF',
    //   filename:t2_date_start+'_to_'+t2_date_end
    // }))));

    // inspector.add(download_kmz)
    inspector.add(download_json)
    // inspector.add(download_img1)
    // inspector.add(download_img2) 
    mapPanel.add(inspector);

  }

});

mainPanel.add(drawButton);